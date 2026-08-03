# AEGIS FINANCE — Full Project Dossier & Forward Research Agenda

**Compiled:** 2026-08-02
**Author:** Claude Opus 5 session, commissioned by Murathan Abdullaev
**Purpose:** A single self-contained document covering (a) everything the project has done, tried, and rejected; (b) an adversarial audit of whether the results can be trusted; (c) external research on maximising ROI; (d) a proposed roadmap.
**Intended audience:** Murathan, plus other AI agents asked to critique this document and bring back findings.

---

## HOW TO READ THIS DOCUMENT

| Part | Contents | Who it's for |
|---|---|---|
| **I** | Executive summary + the seven hard truths | Everyone. Read this even if you read nothing else. |
| **II** | Timeline: what was built, when, and why the philosophy changed three times | Anyone new to the project |
| **III** | The complete experiment ledger — 179 candidates, 31 adjudicated results, 4 survivors | Researchers evaluating the evidence |
| **IV** | Capital allocation: exactly how the money is allocated today, and what changes at $1M | Answers Murat's direct question |
| **V** | **The adversarial audit** — where the results may be faulty | The most important section for critics |
| **VI** | External research: regime switching, LLM alpha, alt-data, portfolio construction | Idea generation |
| **VII** | Competitive position vs open-source projects, firms, and academia | Strategic positioning |
| **VIII** | Optimus (the brain / MCP layer) audit | Infrastructure |
| **IX** | The proposed roadmap, ranked | Decision-making |
| **X** | Questions for critiquing agents | Other AI agents |

**A note on epistemic markers used throughout:**
- **[MEASURED]** — a number produced by this project's own code, with a file reference.
- **[LITERATURE]** — an external published result, with a URL.
- **[DERIVED]** — arithmetic done in this session; verify independently.
- **[SUSPECTED]** — a flaw identified by reading code but not yet empirically confirmed.
- ⚠️ — contested, thin, or single-source evidence.

---

# PART I — EXECUTIVE SUMMARY

## What Aegis Finance is, in one paragraph

Aegis Finance began (2026-03-28) as a free, open-source market-intelligence web platform — Monte Carlo projections, ML crash prediction, portfolio construction, macro risk scoring — and over 128 days and 467 commits mutated into something structurally different: **a research-integrity apparatus with a web front-end attached.** It now runs 10 live paper-trading lanes with a forward-only NAV track record (inception 2026-06-08), a registry of 21 pre-registered trials with decision rules committed before data accrued, a 1,651-line public ledger of 31 adjudicated negative results, and an offline "Strategy Factory" that screened 179 candidate signals through a held-out confirm wall before the search phase was formally closed on 2026-08-02.

## The seven hard truths

**1. The project's research discipline is genuinely exceptional and is its only real moat.**
Nothing in the open-source quant landscape publishes a negative-results ledger with placebo gates that killed the researcher's own designs (§30, §31), a pre-registration protocol with tamper-evident git timestamps, and a forward-only track record. Microsoft's RD-Agent(Q) — the closest competitor, NeurIPS 2025 — publishes only its wins. This is the asset. Everything else in the repo is a commodity.

**1b. THE SURVIVOR LIST IS THREE, NOT FOUR — "insider" is a constant, confirmed on live production data.**
All 72 `insider_opp` observations in the PIT store are **exactly 0.0**; every `insider_cmp` payload shows `n_live_opportunistic: 0`. The live SEC leg returns nothing and has since 2026-06-16, while the collector's own `degraded` flag reports healthy because it only checks *artifact* staleness, never whether the fetch worked. **TRIAL-INSIDER-IC and TRIAL-CMP-INSIDER-IC have accrued zero information.** This is NEGATIVE_RESULTS §5 recurring undetected. Worse, a companion defect (`quantile_return_spread` breaking all-tied ranks alphabetically) manufactures a **+9.6 bp "factor spread" out of a constant** and reports `status: "scored"`. See Part V-B.

**2. Not one signal has cleared the project's own ship gate.**
The ship bar is DSR ≥ 0.95 and PBO < 0.5. Measured values for the survivors: **fusion DSR ≈ 0.10** (after deflating against only 61 candidates), **insider DSR 0.26, PBO 0.41**. gp-small and TSMOM-XA were never run through the gate at all. The four "survivors" are survivors of a *screen*, not winners of a *test*. This is stated honestly inside the project, and must not be softened outside it.

**3. The forward track record cannot ever become the proof — it is an integrity artifact.**
**[DERIVED]** At a true information ratio of 0.5 (optimistic), t = IR·√N years means **16 years to reach t=2** and **36 years to clear Harvey's t>3 multiple-testing bar**. At IR 0.3 it is 44 and 100 years. At day 55 with 10 lanes, the current record has a t-statistic of approximately 0.1. The lanes prove you did not cheat. They will never prove you have skill. Say so explicitly — that admission is itself a publishable contribution.

**4. The core thesis — "beat SPY by mixing strategies and switching on market phase" — is half-supported and half-refuted by the evidence.**
*Mixing* is well-supported. *Switching on regime* is poorly supported for return and moderately supported for risk. **[LITERATURE]** In the cleanest out-of-sample test available (Shu/Yu/Mulvey 2024, net of 10bps and a 1-day delay), the HMM regime-switcher earned **1.7 percentage points per year LESS** than buy-and-hold; its entire Sharpe gain came from de-risking. Every mechanism that survives OOS works by *continuously scaling risk*, not by *discretely selecting strategies*. Meanwhile 70% of professionally-managed tactical allocation funds underperformed a simple balanced index fund.

**5. The binding constraint is not signal quality — it is long-only construction and breadth.**
**[LITERATURE + DERIVED]** Grinold's Fundamental Law with constraints: IR = TC · IC · √BR. At a long-only transfer coefficient of ~0.4 and this project's breadth, reaching IR 0.5 requires IC ≈ 0.125 when real-world signal ICs are 0.02–0.05. This independently predicts NEGATIVE_RESULTS §28's own finding: 99.9% of the `io_level` spread and 88% of `skew_25d` lived in the short leg a long-only book structurally cannot hold. **The project spent months discovering empirically what the Fundamental Law predicts analytically.** Budgeting required IC *before* running a candidate would have pre-empted a large fraction of the 179.

**6. The LLM is essentially unused, and the one place it is wired is dead in production.**
DeepSeek spend to date: **$0.03** of a $19.96 balance. Cause: `daily_call_cap: 150` in `backend/config.py`, sized for a near-zero-cost defensive posture. Worse, EVENT-INTEL — the enums-only extraction subsystem, which is correct and tested — is **never invoked in production**: no scheduler job calls it, its router has zero frontend callers, and its counters reset on every redeploy. It is the project's own CANON §8 "silent fragility" failure mode occurring inside the LLM subsystem.

**7. The most valuable unexploited asset is a free WRDS subscription you probably already have.**
NEGATIVE_RESULTS §4 established that a survivorship-free universe is not buildable on free data (yfinance recovers 1 of 20 delisted names). That single finding has constrained every backtest since 2026-06-16. **HKU Libraries almost certainly provides free student access to WRDS (CRSP + Compustat + IBES).** CUHK, CityU, and Lingnan all do. One email potentially removes the project's single largest methodological constraint at zero cost.

## The one-line recommendation

**Stop searching for alpha. Ship the paper, fix the LLM extraction layer, get PIT data, and rebuild the allocation thesis around continuous risk scaling rather than regime switching.** The search phase closed at 179 for a reason — the evidence says the marginal candidate is worth less than the marginal hour spent writing up what has already been learned.

---
# PART 0 — RESEARCH BRIEF FOR COLLABORATING AI AGENTS

> **If you are an AI agent given this document: this section is your task. Everything after it is evidence.**

## 0.1 The principal's own words

The following is the project owner's brief, reproduced verbatim and unedited. It is the thesis you are being asked to develop, attack, or extend. **Treat it as a hypothesis to be tested, not an instruction to be obeyed.**

> "the main goal is to beat sp500 and maximize roi. I think this will be done by mixing strategies and switching strategies based on the market phase. understanding signals are also a key point thats why i want to utilize llm to understand news on X or journals and public news or stock related news are signals. insider movements etc from data movement of hedge funds and politicians and big investors utilizing them can be better. maybe we can also try to invest with 1milyon dolars I dont now how we are alocating our money how much funds or stocks or how many stocks, are we doing equal shares or weighted based on return?
>
> I am woried our results might be faulty beacuse of how we use data, how we test, the enviroment we created. thats why this session I want to find flaws, find new strats, and research.
>
> is it okay if we lower the confidence to 90 or 85 then? is it acceptable? also do we have to depend on sharpe can we make very risky moves and just maximize roi even more? thats why i said maybe we can swithc strategies based on context.
>
> I think we are in a point where we have data but our aproach should be better, maybe more humanatized. like insiders share holder etc matter how these companies are related their context matters. some unspoken rules of society might not be seen on numbers but we can see that context through news and other sources. on our past project we had all the data and we tried machine learning etc but the winning idea was utilizing social biasses, we are bound to make decisons based on our biases, emotions thats why news coverage, public and ivestor opinions matter. there are a lot of profitable companies and they are not increasing and undervalued since they are not mainstream or other biases. on the other hand there are a lot of over valued companies nvida, tesla etc and they still increase since they are always on the news. we talked that following trends fail but if we get in early and drop at the peak of their trend we can make profit thats how hedge funds and investors maximize.
>
> a companies stance on politics, their founders, network, social and political influence also guide their price and we cant get them just from the numbers thats why LLM is supposed to be used like a brain with our optimus combined in my theory. think outside the box, sometimes the simplest solutions works the best, where numbers support context and logic might not or vice versa. even a companies name, how many people from a certain ethnic background, their closeness to the ruling party, their out look on media matters a lot. we need to figure these key points too perhaps.
>
> we cant always be certain since we are looking at probobilities make more riskier moves and keep it safe when have to, if we push for protecting the money and take no risks, we cant maximize neither maybe confidence level above 60 is better I am just trying to find new aproaches, brainstorm with me. prove me right or wrong, find more ideas like these maybe from internet, project, research papers etc."

## 0.2 What has already been answered — do not re-derive these

Part IX scores this thesis claim by claim. In summary:

| Claim | Verdict | Where |
|---|---|---|
| Mixing strategies beats a single strategy | ✅ Right | VI.1a |
| Switching on market phase beats holding | ❌ Wrong for return, right for risk | VI.1b |
| Social/narrative bias creates durable mispricing | ✅ **Right, and under-exploited here** | IX.4 |
| Networks, founders, political connections matter | ✅ **Right, measurable, and the data is already downloaded** | IX.4, 0.3 |
| Ethnic composition as a signal | ❌ Wrong — bad measurement, unacceptable exposure | IX.4 |
| Get in early on trends | ✅ Right | IX.3 |
| Exit at the peak | ❌ Refuted by the project's own §1 | IX.3 |
| LLM as a brain with Optimus | ✅ Right **as an extractor**, not a predictor | VIII.5 |
| Lower the confidence threshold | ⚠️ Partly — but it is a power problem, not a threshold problem | IX.1, V-C.3 |
| Maximise ROI not Sharpe | ✅ Right objective (maximise μ − σ²/2), wrong risk type | IX.2 |

## 0.3 The material fact that changed on 2026-08-02

**WRDS data is already downloaded locally and is substantially unexploited.** Verified inventory at `C:\Users\mrthn\Aegis module\data\` (2.0 GB in `wrds_raw/` alone):

| File | Content | Status |
|---|---|---|
| `crsp_dsedelist.parquet` | **38,872 delisting events, 25,616 delisting returns**, full `dlstcd` codes | Used by the factory |
| `crsp_stocknames.parquet` | 83,280 name records with `namedt`/`nameenddt`, 1925–2024 | **This is what solves ticker reuse** |
| `crsp_msf.parquet` | 1,145,001 monthly obs, 2002-01→2024-12, `dlret`/`dlstcd` joined | Used |
| `crsp_panel_1963/`, `crsp_panel_2002/` | Monthly returns, prices, dollar volume | Used |
| `dsf_full/`, `dsf_monthly_agg*.parquet` | Daily stock file + aggregates | Used |
| `ccm_link.parquet` | 33,324 CRSP↔Compustat links with `linkdt`/`linkenddt` | Used |
| `comp_funda*.parquet`, `comp_fundq*.parquet` | Compustat annual + quarterly fundamentals | Used |
| `insider_panel.parquet` (20 MB), `sec_insider/` (869 MB) | Insider transactions | Used |
| `revision_panel.parquet`, `sue_events.parquet` | Analyst revisions, earnings surprises | Used |
| **`boardex_company_networks.parquet` (43 MB)** | **Board interlock network** | ⚠️ **DOWNLOADED, NEVER USED** |
| **`boardex_dir_profiles.parquet` (44 MB)** | **Director profiles — education, employment history** | ⚠️ **DOWNLOADED, NEVER USED** |
| **`boardex_org_summary.parquet` (22 MB)** | **Organisation summaries** | ⚠️ **DOWNLOADED, NEVER USED** |
| `reference/osap_SignalDoc_snap20260726.csv` | Chen-Zimmermann Open Source Asset Pricing signal doc | Snapshotted |

**Two consequences that reframe this whole document:**

1. **NEGATIVE_RESULTS §4 ("a survivorship-free universe is not buildable on free data") is TRUE but no longer BINDING for research.** It describes the *production backend*, which runs on yfinance. The **research module already runs on CRSP with delisting returns and permno-based identity**, which is why the 179-candidate factory results are more trustworthy than §4's caveat implies. **The paper must state this distinction precisely — it currently does not, and the conflation understates the research's own quality.**
2. **BoardEx is the single largest unexploited asset in the project, and it is exactly the data the principal's thesis calls for.** Cohen, Frazzini & Malloy (JPE 2008, "The Small World of Investing") and (JF 2010, "Sell-Side School Ties") show board and educational network connections predict returns. The principal asked for "founders, network, social and political influence." **That data is on disk, 109 MB of it, and has never been opened.**

### ⚠️ 0.3b — BUT THE BOARDEX EXTRACTS ARE TRUNCATED AND UNUSABLE AS-IS

Direct inspection (2026-08-02) found a blocking defect. **Do not build a signal on these files until they are re-pulled.**

| File | Rows | Tell |
|---|---:|---|
| `boardex_org_summary.parquet` | **exactly 500,000** | Round cap |
| `boardex_dir_profiles.parquet` | **exactly 1,000,000** | Round cap |
| `boardex_company_networks.parquet` | **exactly 1,000,000** | Round cap |

**Three files landing on exact round numbers is a SQL `LIMIT`, not a natural row count.** Corroborating evidence:

- `boardex_company_networks` contains only **3,240 unique `boardid`** — BoardEx covers tens of thousands of listed firms. This is a small, arbitrary slice of the network.
- `boardex_org_summary` has **11,007 unique `boardid`** across 500k rows.
- Coverage **declines sharply in recent years**: `annualreportdate` counts run 2021: 11,479 → 2024: 7,404 → 2025: 2,091 → 2026: 87. Some of that is genuine reporting lag; the shape is also consistent with truncation.

**Why this is disqualifying rather than merely inconvenient:** a `LIMIT` without an `ORDER BY` returns whatever the query planner emits, which is typically clustered by id or insertion order — i.e. **non-random selection on entity**. A network signal built on a non-randomly selected 3,240-firm subgraph would have exactly the failure mode this project already caught once, in §20, where the *eligibility rule* rather than the hypothesis produced the effect. Network centrality is especially vulnerable: **centrality computed on a truncated graph is not a noisy estimate of true centrality, it is a different quantity.**

**Required before any BoardEx work (this is now the concrete WRDS task):**
1. Re-pull all three tables with **no row limit**, explicitly scoped — US-listed, `orgtype` filtered, date-bounded — and record the row counts so truncation is detectable.
2. Establish the PIT rule. `dir_profiles` is PIT-capable by construction (`datestartrole` / `dateendrole`, with `9999-12-31` as the open sentinel), but check `datestartroleflag` / `dateendroleflag` (values 10–80), which encode date *precision* — an imputed date is not an observable one.
3. Build the linkage: `org_summary` carries `cikcode` (487,919 non-null) and `ticker` (467,376) → join to CRSP via CIK, or via ticker **through `crsp_stocknames` with `namedt`/`nameenddt`**, never on a raw current ticker.
4. **Construct the network graph as-of each rebalance date only.** `boardex_company_networks.overlapyearend` uses the string `"Curr"` for open links (77,308 rows) — treating `"Curr"` as a known end date is a look-ahead.

## 0.4 What collaborating agents are asked to produce

**Do not** re-run the audits in Parts V, V-B, V-C — they are done and several were verified by direct computation. **Do** attack the following.

### Priority 1 — The BoardEx network thesis (highest value, data in hand)
Design a **pre-registrable** signal from `boardex_*.parquet` + CRSP. Specify: hypothesis, construction, universe, the exact PIT rule (BoardEx has appointment/resignation dates — establish what is knowable at time *t*), primary metric, decision rule, earliest decision date, **and the required IC given the Fundamental Law budget in VI.2c.** Cite Cohen-Frazzini-Malloy and state the honest prior including post-publication decay. **Flag any leakage channel specific to network data** — in particular, network centrality computed on the full-sample graph is a look-ahead of exactly the kind that killed the FRED features (Part V-B, L3).

### Priority 2 — The neglect × quality interaction
Part IX.4 proposes it; nobody has built it. Media/analyst coverage counts are the neglect proxy (IBES if licensed, else 10-K/news counts). **First check whether it already exists among Chen-Zimmermann's 212 predictors** — the SignalDoc snapshot is on disk at `data/reference/`. If it exists, report its documented decay instead of proposing a re-discovery.

### Priority 3 — The borrow-fee eligibility filter
Part VI-B.1 argues this is the highest-EV idea available and that it retrospectively explains §26 and §28. Two open questions: (a) does IBKR still publish free borrow-fee files, with what history? (b) can the **option-implied borrow fee** (`h ≈ −(σ_C − σ_P)/√(2π(T−t))`) be reconstructed from data on hand? Design it as a **universe rule, not a signal.**

### Priority 4 — Attack the arithmetic
Parts V-C.1 and VI.2c contain the load-bearing numbers. **Try to break them.** Specifically: is Z(179) = 2.729 the right deflation for this search given that candidates are correlated across families? What is the honest effective N after clustering? Is TC ≈ 0.4–0.6 right for a 50-name long-only book?

### Priority 5 — The risk-appetite question, properly posed
The principal wants maximum ROI and accepts high risk. Part IX.2 argues the objective is `g = μ − σ²/2` and that the right lever is **systematic, not idiosyncratic** risk. **Stress-test that.** Under what conditions does a young investor with large human capital and a 30-year horizon rationally exceed half-Kelly? What does the lifecycle literature (Merton; Campbell-Viceira; Ayres-Nalebuff "Lifecycle Investing") actually license? Give a number, not a posture.

### Ground rules
- **Cite or don't claim.** Every empirical assertion needs a source; every internal claim needs `file:line`.
- **State your prior before your result.** The project scores its own predictions and is currently 0-for-4 on family-stage calls.
- **A negative result is a deliverable.** The primary output of this project is a paper about 179 failures.
- **Nothing an LLM produces may allocate.** The LLM narrates and extracts; a deterministic, tested engine computes. This is CANON §3 and it is not negotiable.
- **Assume the results are wrong and hunt for the mechanism.** That instruction produced every finding in Parts V and V-B, including two confirmed fabrications in live production data.

---
# PART II — TIMELINE: WHAT WE DID AND WHY THE PHILOSOPHY CHANGED

467 commits, 2026-03-28 → 2026-08-02 (128 days). Commit cadence by phase: an intense build sprint in April (36–71 commits/day on peak days), a quiet May, then a sustained research cadence from June onward (5–26 commits/day).

## II.1 Phase table

| Dates | Phase | Built | Decided | Abandoned |
|---|---|---|---|---|
| 03-28 → 03-31 | Pre-V1 scaffold, Phase 0–3 audit | Full stack (Next.js + FastAPI); Monte Carlo jump-diffusion, crash model, macro dashboard, sector analysis, portfolio builder, signal engine | Reproducibility standard (`SimpleImputer` not `fillna(0)`; purged CV) | — |
| 04-11 → 04-17 | Autonomous overnight lab, ~83 cycles (V7–V10) | `lab/rd_loop.py`; GARCH, HMM, block bootstrap, drift detection, options/earnings intel, tail risk, Cox PH survival, BOCPD changepoints, copula tail dependence, RMT covariance denoising, vol cone | Alternating "deep integration"/"deep audit" cadence | — |
| 04-17 (V11–V13) | Feature sprint | Style box, factor grades, treemap, allocation backtester, AI copilot, provider registry, ownership look-through, tearsheets, convex optimizer + MPC, Python SDK, bonds, EDGAR 8-K, ESG, FX/commodities/crypto, multi-currency | Feature-breadth strategy pursued to its limit (~45+ features) | — |
| 04-26 → 05-02 | Portfolio Intelligence (PI) subsystem | 4-lane data model, rules engine, replay, APScheduler, 4 frontend pages | PI specced as the seed of the forward track record | — |
| **06-06 → 06-08** | **V1 ship — the honesty spine begins** | PBO/DSR/CPCV overfitting guards, direct-IC factor validation, shared MTM NAV engine, experiment registry, cash sleeve, deploy canary | **"V1 freezes the engine set. No new engines… consolidation, not expansion."** | Two pre-launch bugs caught: optimizers silently falling back to equal-weight; lanes never marked-to-market |
| 06-10 → 06-11 | V2 P0 + TRIAL-001 | Live NAV curve, `/api/health/full`, track-record UI. **TRIAL-001 (HRP vs EW) pre-registered 06-11** | "If it isn't pre-registered, it didn't happen" | — |
| **06-14** | **Fragility reframe (inflection #1)** | Fragility composite, LPPLS flag, mirror + conviction book lanes | **Crash thesis reframed: "time the crash" → "measure fragility, scale exposure."** `V3_SCOPE.md` titled "the v2→v3 pivot boundary" | Crash *timing* as a goal |
| 06-15 → 06-17 | V3 thematic momentum + exit discipline | Chandelier/ATR exits, theme baskets, 12-1 momentum. `conservative-atr` lane seeded | Murat's challenge: "prove me wrong with real values" | **TRIAL-THEME REJECT** (−0.08 Sharpe, PBO 0.66). **T7: yfinance recovers 1/20 delisted names → forward-only validation doctrine for the rest of the project** |
| 06-20 | V3 build sprint | Data-integrity gate, forward-IC scorecard, feature-hash guard, data-grade stamping | **"Backtest = falsifier ONLY"** formalized | `crash_model.pkl` retrain fixed but AUC unusable — deploy HELD (still broken today) |
| **07-08** | **CANON.md written (inflection #2)** | 5 discipline skills, conviction decision-logging UI, fragility collectors | **11 standing rules codified — the project gets a constitution** | — |
| 07-09 → 07-12 | Trials sprint | PEAD/quality IC collectors, per-position guidance, CONGRESS-IC, ARK-IC, SMARTGROWTH, `/dev` dashboard | — | `ipo_issuance` false-zero bug (read `hits.total.value` wrong; prod silently returned 0) |
| 07-14 → 07-17 | **V4 — "a quant desk for the average person"** | 429→503 honesty, ticker resolver, daily brief, Railway RAM levers, FORECAST-LEDGER, Alpaca mirror infra, quantstats tearsheets, FMP key-leak fix | Forward record at day 39, explicitly flagged as noise | **TRIAL-CRASH-2 REJECT** (0/6 dense cells) — third confirmation crash-timing skill ≈ 0 |
| **07-18 → 07-19** | **V5 "Honest History" (inflection #3)** | EODHD Phase-2 gate FAIL → cancelled, but 50,462 histories harvested first. Alpaca mirror seeded. Factor Lens | **Successor arc named "THE INVESTOR BRAIN" — the project reorganizes around a research factory** | **MOM-BACKTEST #13 FAIL**, **MOM-TREND #14 FAIL worse** — momentum lane CLOSED |
| 07-21 → 07-22 | Brain adopted; Strategy Factory built | BRAIN-003 insider promoted; **explore(2004–2018)/confirm(2019–2024) wall becomes binding protocol**; SMQ lane seeded | The wall becomes the central research-integrity mechanism | — |
| 07-24 → 07-26 | Research sprint; candidates 88→155 | 5 candidate batches, 7+ AI-panel rounds, TSMOM-XA found, CZ-CALIB + HARNESS-VALID exhibits | **PROJECT_REPORT §7 "WHERE THE PIVOT IS": from searching for edge to compounding proof** | JM regime rotation, target-price rebuild, theme-supply, conc_low all closed. **NAV re-book defect found + history reconstructed** |
| 07-28 → 07-29 | **FREEZE at 158** | Red team (4/5 candidates DEAD), EVENT-INTEL spec, FF vintage pinned, D1–D4 diagnostics | Data strategy: spend $0/mo. Belief-engine Phase 2 BLOCKED by its own kill-first diagnostics | **COND-VT REJECT** — third allocation instrument killed by the confirm wall |
| 07-30 | Rounds 13–15 | Adverse priors declared before decision dates; external briefing written | Panel finding: **"the data shelf is empty"** | — |
| 08-01 | Round 16 | Mirror capture diagnostic (up-capture −0.98 → concentration, not timing) | **New rule: every control-armed design carries a random-date placebo gate** | 13F family closed (§26); option-implied family closed, all 7 arms (§27) |
| **08-02** | **Search phase CLOSES at 179** | RANK-DEAD diagnostic solves rank-real/book-dead; 13DG event PASS then two placebo gate firings; shuffled-CV leakage demo; panel-cache fix | **Explore queue empty. Remaining work: verification + write the paper** | 13D/13G family closes UNMEASURABLE — the terminal result of the search phase |

## II.2 The philosophy shift, precisely

The change from "feature-rich web app" to "research discipline" was not one event. It escalated in three stages:

1. **Proposed in principle** — 2026-06-14, V2→V3 freeze language.
2. **Operationally organized** — 2026-07-18, the "Investor Brain" arc begins.
3. **Formally declared and executed** — 2026-07-26 report → 07-28 freeze at 158 → 08-02 close at 179.

The cleanest before/after artifact pair is `ABSTRACT.md` (undated, pure ML/methodology sell, no mention of lanes or trials) versus the current `README.md`, which opens: *"Aegis Finance is a free, open-source market-intelligence platform with an unusual spine: it measures itself in public and tells you when it's wrong."*

## II.3 The ten paper lanes

| # | Lane | Seeded | Config hash | Represents | NAV 07-31 | Since inception |
|---|---|---|---|---|---|---|
| 1 | conservative | 2026-06-08 | `82be14cb6039bfae` | Template mandate | $101,373 | **+1.37%** |
| 2 | balanced | 2026-06-08 | `82be14cb6039bfae` | HRP arm of TRIAL-001 | $101,777 | **+1.78%** |
| 3 | aggressive | 2026-06-08 | `82be14cb6039bfae` | Template mandate | $102,713 | **+2.71%** |
| 4 | balanced-ew-control | 2026-06-11 | `628456e4` | Frozen EW control | $97,886 | **−2.11%** |
| 5 | mirror | 2026-06-16 | `d0d0eaf4…` | Aegis rules on Murat's real book | $77,565 | **−22.44%** |
| 6 | conviction | 2026-06-16 | `d0d0eaf4…` | Murat's logged discretionary calls | $90,132 | **−9.87%** |
| 7 | conservative-atr | 2026-06-17 | `5196232381dd4a7e` | ATR trailing-stop overlay | $103,594 | **+3.59%** |
| 8 | smallmid-quality | 2026-07-22 | `7347b69af584b7b8` | fusion (gp-small ⊕ insider), 30 names vs IWM | $97,203 | **−2.80%** |
| 9 | tsmom-overlay | 2026-07-27 | `a244d7ab7374b49c` | Cross-asset trend overlay | $100,102 | **+0.10%** |
| 10 | tsmom-6040-control | 2026-07-27 | `a244d7ab7374b49c` | Frozen 60/40 control | $100,107 | **+0.11%** |

Plus an Alpaca paper account (`PA32NSWMCJ6P`, seeded 07-18) providing third-party NAV verification of the mirror lane.

⚠️ **All ten numbers above are statistically meaningless.** Inception 2026-06-08, age 55 days. Interpreting the −22.4% mirror or the +3.6% ATR lane as evidence of anything is exactly the error the 24-month rule exists to prevent.

### Breaks in the record (both documented, both fixed)

- **NAV re-book defect** (found 07-26): `_apply_rebalance_positions` sized every rebalance off the static $100k inception value instead of live marked NAV, partially resetting lanes toward 100k on every rebalance. Proof: SPY +0.85% on 07-09 while the aggressive lane showed −2.79%. Fixed (`36c8ece`); history reconstructed in prod 07-27 under env gate, originals archived. Correction factors: mirror ×0.8511, conviction ×1.0260, aggressive ×1.0109, conservative-atr ×1.0221, balanced-ew-control ×0.9939.
- **Panel-cache poisoning** (found/fixed 08-02, `451ad98`): the shared price-panel cache key omitted the ticker set, so whichever lane fetched first each day poisoned the panel for all others. **Open verification item: confirm TSMOM's first real rebalance fires ~08-03 after 16:30 ET.**

## II.4 What was planned and never done

**Two attended decisions still open:**
1. **Mirror/conviction concentration control** — the 08-01 capture diagnostic found the mirror lane's problem is concentration, not timing. The fix is a mandate call Murat owns.
2. **Un-park the paper** — writing was paused until the search closed. The search closed 08-02. Drafting has not resumed.

**Backlog never executed:** T12 (N-PORT + Chen-Zimmermann harness); U1/U2 (page merge, parallelization); T13 (max-growth lane pre-registered, never seeded); H1/H2/H5 (untrack lab scratch, dependency lockfile, **`except Exception` swallower audit — ~70 of 469 sites**); M2/M4 (Brier-CI headline regen, README repositioning); V2/V4 (server-side conviction persistence + alert engine — **never built at all**); V6–V8 (UI rework, optimizer honesty, tiered coverage) — parked; B7 (quantstats tearsheets — installed, never imported).

**Standing unresolved:** `crash_model.pkl` has been broken continuously since mid-June. Overlay reads `model_not_deployed` in prod on all four armed-capable lanes. TRIAL-CRASH-2 (the successor) was also rejected. This is backlog item M3.

**Never built despite being ruled admissible:** capital-flows research family (ETF flows, positioning, gamma); BoardEx board-connection signal (access confirmed 07-24); the go-public launch plan (proposed 07-12). `CAPABILITY_MATRIX.md` still lists ~60+ of ~104 services as UNAUDITED.

**PDUFA ledger:** 7 pre-registered biotech-approval calls, unscored. First matures ~2026-08-24.

## II.5 Documentation defects found while compiling this dossier

- `docs/TRIALS/TRIAL-002-mirror-vs-rules.md` and `TRIAL-003-conviction-vs-rules.md` still read **"lane not yet seeded"** — both lanes went live 2026-06-16 (commits `5902fff`, `064aa82`). The trial docs were never updated after seeding.
- `optimus/docs/ARCHITECTURE.md` still says *"Not built: distill, MCP server, daemon, router, lint, audit"* — the MCP server and audit are both built and in daily use.
- `ABSTRACT.md` describes a version of the project that no longer exists (no mention of lanes, trials, or the negative-results ledger). It is the document most likely to be read first by an outsider.

---
# PART III — THE COMPLETE EXPERIMENT LEDGER

## III.0 Two counters, never conflate them

The project runs **two separate trial-counting systems**, and every external reader gets this wrong:

1. **Strategy Factory / brain module** (external repo `investing-test-module`) — the offline explore(2004–2018)/confirm(2019–2024) research harness. Cumulative candidate counter: **179**. Explore queue empty as of 2026-08-02.
2. **Aegis production trial registry** (`backend/services/portfolio_intelligence/experiment_registry.py`, SQLite `rule_experiments`) — governs the **21 pre-registered forward trials/lanes** in `docs/TRIALS/`. Live `cumulative_trials` = **18**. This is what the live DSR/PBO ship gate deflates against.

**⚠️ This is a genuine methodological problem, flagged in Part V.** The ship gate deflates against 18, but the true search burden that produced the survivors is 179. The deflation is understated by an order of magnitude in trial count.

Backtest priors from (1) are never treated as evidence in (2) — they only set an "honest prior" in a forward trial's pre-registration document. That firewall is correct and well-maintained.

## III.1 Adjudicated results — all 31 sections of NEGATIVE_RESULTS.md

| § | Name | Tested | Method | Result | Verdict |
|---|---|---|---|---|---|
| 1 | Signal-engine timing | Composite signal as market-timing tool | 2020-01→2025-06, 66 monthly signals | Strategy **+250.9%, Sharpe 0.675** vs B&H **+740.0%, Sharpe 0.921**; sell-signal 3M hit rate **28.6%** (target >55%) | **REJECT** — sell signals fire at VIX>25, historically the best buying opportunity |
| 2 | 12-month crash prediction | LightGBM/Logistic at 12m | Walk-forward Brier vs climatology | 3m Brier **0.046** (beats base rate, but on ~7 events); 12m ≈ climatology | **NO SKILL at 12m** |
| 3 | LPPLS bubble timing | Log-periodic power-law predictive skill | Two independent adversarial tests | Refuted 2/2 | **REFUTED** → descriptive flag only |
| 4 | Survivorship-free universe on free data | Can yfinance supply delisted names? | 20 real delisted S&P names | **15/20 nothing, 4/20 wrong company (recycled symbol), 1/20 usable = 5%** | **UNBUILDABLE** — the constraint on every subsequent backtest |
| 5 | Insider collector prod fetch | Does the collector actually fetch? | 12/12 offline tests green; live prod check | **100% of SEC Archives fetches 403'd in prod** | **PROCESS FAILURE** (fixed via `_sec_get` choke-point) |
| 6 | Crash-model M3 retrain | Binary ≥20% drawdown label | Walk-forward AUC | **AUC unmeasurable** (zero events in purged validation windows); 6m head std 0.00pp | **REJECT / held** — rare-event label unlearnable |
| 7 | TRIAL-CRASH-2 severity model | Per-cell LightGBM exceedance | 5-fold expanding WF 2016–2026, purge 63td/embargo 21td, vs climatology AND STLFSI4 | **0/6 dense cells passed**; skill −0.32 to −0.54 at 5% cells | **REJECT** — 3rd confirmation crash timing ≈ 0 |
| 8 | EODHD data acceptance | Paid survivorship-free source, pre-registered gate | 20-name delisted audit, bar ≥16/20 | **14/20** (phase-1's "16/20 PASS" was itself inflated) | **FAIL** → subscription cancelled after $19.99 |
| 9 | 12-1 momentum (TRIAL-MOM-BACKTEST) | Long-only top-50 EW | 50,462-name panel, 2017-01→2026-06 | CAGR **17.9%** / Sharpe **0.629** / maxDD **−54.7%** vs SPY 15.3% / 0.871 / −33.7% | **FAIL** — beat SPY's return, still uninvestable |
| 10 | Trend-filter rescue | + SPY 10-month SMA cash filter | Same panel | CAGR **4.8%** / Sharpe **0.307** / maxDD **−61.3%** — worse on every metric | **FAIL, inquiry CLOSED** |
| 11 | FDA approval drift (monthly) | Post-approval drift | 671 matched NDA/BLA approvals 2002–2024 | Arm B **−30.1 bps/mo (t −0.89)**; gross also null | **REJECT** — not even a cost story |
| 12 | Supplier momentum (slow basket) | Sales-weighted customer momentum | Explore 2004–2018 | B−A spread **t 0.10**; micro top decile **−80.8 bps/mo (t −4.27)** | **REJECT, both kill conditions** |
| 13 | `conc_low` (TRIAL-BRAIN-010) | Diversified-customer suppliers | Explore → confirm | Explore: net t **2.28**, IC t **4.46** (passed both legs) → **Confirm: −5.5 bps/mo (t −0.20), DSR 0.0003** | **KILL at confirm** — first live-fire wall validation |
| 14 | Self-deception ceiling + PEAD | Mining ceiling of the 53-signal library | Full-window 2004–2024 | Pick-best **t 2.94**, top-5 composite **t 3.27** ≈ zero-skill max **t 3.6–4.0**; with sign-flips **t 6.16/6.58, Sharpe 1.44**; `pead_agree` IC **t −2.6** | **Ceiling measured; PEAD INVERTED** |
| 15 | Jump-model regime rotation | Single-safe-asset rotation | Explore → confirm | Explore CAGR 11.2% vs SPY 7.7%, maxDD −26.6% vs −55.2% (passed all 3) → **Confirm: 2022 cost −21.6%** | **REJECT, CLOSED** — explore pass was one crisis wearing three bars |
| 16 | FDA drift (daily) | Daily-resolution successor | 500 NDA/BLA approvals 2002–2018 | CAR(+1,+20) **+2.1%, t 1.45** vs bar 2.0 | **REJECT** — drift is in days 1–5 in HIGH-attention events |
| 17 | Analyst price targets | Raw upside + low-dispersion | WRDS batch-4 | Raw: largemid **−90 bps/mo (t −3.62)**, small **−199 bps/mo (t −7.21)** | **REJECT both arms** — analyst-source pickers 0-for-3 |
| 18 | Inflation-gated GLD reroute | Post-hoc repair of §15 | Explore → confirm | Confirm calendar-2022 **−23.9%** — *worse* than the thing it repaired | **REJECT** |
| 19 | LLM/agent trading alpha | External evidence sweep | 3 receipts | Flagship paper **withdrawn**; FINSABER kills agent alpha post-cost; Glasserman-Lin: "not a feasible strategy" | **CLOSED (external)** |
| 20 | Distress-8-K exclusion filter | 8-K as exclusion screen | 4,860 EDGAR indexes, 3,949 events | Treatment **−5.95% (t −7.06)**; **displaced-time control −6.79% (t −11.33) — control BEAT treatment** | **UNADJUDICATED** — selection, not information |
| 21 | Conditional vol targeting | Extremes-only VT | Explore → confirm | Explore Sharpe 0.615 vs SPY 0.497 → **Confirm 0.836 vs 0.897, maxDD identical to SPY to 4 decimals** | **FAIL confirm** — 63-day window too slow for 2020 |
| 22 | Small-cap shelf cost re-scan | Was the cost model over-penalizing? | 5-signal cohort, 3 cost arms | KO half-spread actually **11.6–13.1 bps** vs assumed flat 25–50 (**2–4× over-penalty**); **0 graduates after correction** | **CLOSED, 0 verdicts changed** |
| 23 | Residual momentum | FF3-residualized vs total momentum | Explore, corrected after a VOID | Small IC **t 0.81** vs control `mom_12_1` IC **t 3.05** | **REJECT, family CLOSED** — the info was the factor tilt |
| 24 | Flow-vs-level synthesis | 19 flow signals | Synthesis, no new run | `text_jac` IC t **7.47** → net t **0.87**; only **3/19 net-positive** | **Finding** — differencing raises IC and destroys tradability |
| 25 | Cost-ruler cross-check | Corwin-Schultz vs Kyle-Obizhaeva | 24.0M rows CRSP 2002–2024 | CS/KO ratio **7.6–9.1×** large/mid; level gate FAIL | **"KO understates costs," verdicts unchanged** |
| 26 | Abnormal institutional ownership | `io_level`, `io_chg`, `io_abn` | Explore only | `io_level` small **IC t 11.29**, gross t **+0.02**; `io_chg` largemid **t −3.34** (predicted highest, came in lowest) | **ALL 3 REJECT** — residualisation removed information |
| 27 | Option-implied family, 7 mechanisms | iv_atm, riv_spread, skew_25d, term_slope, os_ratio, pc_volume, skew_resid | 14 deciding cells, OptionMetrics, 23 years | Best zero-cost gross **t +1.02**; **DSR 0.0000 in every cell at n=173**; `os_ratio` **−92.3 bps/mo**, opposite of published direction | **ALL 7 REJECT, family CLOSES** |
| 28 | RANK-DEAD diagnostic | Why huge IC + dead books? | L1 decile spread vs L2 vs mirror | **`io_level`: 99.9% of spread in the SHORT leg. `skew_25d`: 88%** | **SOLVED** — long-only structurally cannot harvest it |
| 29 | 13D activist filings (event level) | CAR around 13D vs 13G placebo | n=9,431 / 59,598 | 13D +1..+5 **+96.6 bps (t 4.75)**; 13G placebo −3.3 bps (t −0.40) | **PASSED CAR gate — first event family to clear.** Book stage: −44.9 bps/mo, inside placebo range |
| 30 | 13DG-HARVEST | Can a monthly entry harvest §29? | Placebo gate read FIRST | Placebo pooled clustered **t −3.17** vs bar \|t\|<2.0 — **GATE FAILED** | **NO CONCLUSION** — real number never computed |
| 31 | 13DG-HARVEST2 (terminal) | Size + prior-return matched control | Same gate, terminal clause pre-declared | Placebo **t −3.02** — **GATE FAILED AGAIN** | **Family CLOSES as UNMEASURABLE.** Candidate #179. Search phase closed |

## III.2 The four survivors — and what they actually measured

All four originate as **backtest results in the offline brain module** and now run as **forward-only paper instruments**. **None has cleared the production DSR/PBO ship bar.**

| Survivor | Measured numbers | Gate status | Forward instrument | Caveats |
|---|---|---|---|---|
| **gp-small** (small-cap gross profitability) | Explore **+23.2 bps/mo** net; confirm PASS **+24.1 bps/mo**, IC **t 4.29**; 1982–2001 extension **+18.8 bps/mo** | **Never independently gated** | Embedded inside TRIAL-SMQ-FWD | **FF6 alpha negative** — the edge may be factor tilt, not skill |
| **insider** (CMP opportunistic insider) | Large/mid **+17 bps/mo** (net t 1.40); **FF5+UMD alpha +102 bps/mo (t 1.89)**; microcap **null**; net Sharpe 0.52 | **FAIL: DSR 0.26 at n=24, PBO 0.41** | TRIAL-CMP-INSIDER-IC, decision 2027-07-21 | Self-described as "a weak positive prior, not a discovery." Declared adverse prior 2026-07-30: CMP literature decayed ~60–70% post-2010 → expect **30–40 bps/mo** |
| **fusion** (gp-small ⊕ insider) | **+15.3 bps/mo net, NW t 1.66**; beats best single signal using 3.6× the names | **FAIL: DSR ≈ 0.10** after 61-candidate deflation (bar 0.95) | TRIAL-SMQ-FWD, `smallmid-quality` lane, 30 names, decision **2028-07-22** vs IWM | No skill claim possible before 2028 |
| **TSMOM-XA** (cross-asset trend overlay) | Confirm crisis alpha both held-out crises: **2020 +9.2%, 2022 flat**; overlay maxDD **−18.8%** vs SPY **−33.7%**; return drag **t −1.86**; 2019–24 CAGR 10.2% vs SPY 17.1% | **Never run through the gate** (framed as crisis-alpha, not beat-SPY) | TRIAL-TSMOM-XA + 60/40 control, 24mo | Explicitly **a defensive diversifier, NOT a beat-SPY engine.** Adverse prior: ~40% of TSM returns trace to macro-exposure timing, not a standalone trend premium. At day 52 it trailed its control by 0.68pp on a window with no drawdown to protect against |

## III.3 The 31 results grouped by failure mode

| Theme | Count | Sections |
|---|---|---|
| Structural mechanism wrong on timing/trend | 4 | §1, §9, §10, §16 |
| **Died at held-out confirm after passing explore** | 4 | §13, §15, §18, §21 |
| **Rank-real / long-only book-dead** (~23 individual arm results) | 4 | §23, §26, §27, §28 |
| Housekeeping about the search itself | 4 | §14, §22, §24, §25 |
| **Killed by its own placebo gate before a result existed** | 2 | §30, §31 |
| Weak/absent effect measured directly | 3 | §2, §11, §12 |
| Rare-event label unlearnable | 2 | §6, §7 |
| Data source failed its own acceptance gate | 2 | §4, §8 |
| Sign-inverted anti-signal | 1 (+2 secondary) | §17 (also §14, §27) |
| Silent-fragility process failure | 1 | §5 |
| External evidence closure | 1 | §19 |
| Selection/eligibility bias (control beat treatment) | 1 | §20 |
| Event-level pass, book-level selection failure | 1 | §29 |
| Predictive skill adversarially refuted | 1 | §3 |

**Two cross-cutting patterns worth naming:**

- **Residualisation destroys information** — replicated in three independent construction classes: factor-return residual momentum (§23), firm-characteristic residual ownership (§26), option-implied residual skew (§27). Now a standing house prior: any future "abnormal X" signal starts with three receipts against it.
- **Control/placebo gates are the load-bearing discipline** — four instances: §20 (control beat treatment, discovered *after* the fact), §29 book stage (random-date placebo reproduced the effect, discovered after), §30 and §31 (placebo pre-registered as a mandatory **gate read before the result**). The evolution from "discovered after" to "gate read first" is the single most impressive methodological development in the project.

## III.4 Guards invented in response to a specific failure

| Guard | What it does | Motivated by |
|---|---|---|
| **Random-date placebo GATE, read before the result** | Blocks computing the real number if a randomised-date null doesn't clear \|t\|<2.0 | §20 → formalized after §29 → executed §30, §31 |
| **DSR/PBO deflation against cumulative, never per-batch** | Bar tightens over the project's life | TRIAL-001 design review; reinforced by §4 (guards don't fix a biased universe) |
| **Zero-cost bound as the decisive column** | Proves a verdict can't change under any cost model | §22, reused in §25, §26, §27 |
| **Block-bootstrap Brier CI (not i.i.d.)** | Accounts for autocorrelated overlapping crash labels | §2 (headline Brier on ~7 events overstated certainty) |
| **Explore/confirm wall, confirm untouched until explore passes** | The central integrity mechanism | Validated live-fire by §13 |
| **Pre-declared scored predictions** | Forces a falsifiable claim before the number exists; scored N-of-M | §26, extended across §26–§31 (**house went 0-for-4 on family-stage predictions**) |
| **Repair-before-result discipline** | A fix is legitimate only if made before any number was visible | §26, §27, §30, §31 |
| **Terminal clause** | Pre-commits that a family closes in a given branch regardless of outcome | §31 — invented because §30's NO CONCLUSION needed an ungameable exit |
| **Two-phase money gate for paid data** | Cheap fence, then paid-verification fence | §8 — capped loss at one $19.99 month |
| **Live-prod verification (not green tests)** | `verify-prod-after-deploy` skill | §5 (12 passing tests, 100% prod failure) |
| **Harvey-Liu-Zhu t≥3.0 hurdle** | Higher multiple-testing-aware bar | Calibrated by §14 (zero-skill max t≈3.6–4.0; **t≥7 = bug, not alpha**) |

## III.5 The multiple-testing burden, quantified

- **Ship bar:** DSR ≥ 0.95 **and** PBO < 0.5.
- **At n_trials = 173** (§27 option cohort), the expected max Sharpe under the null was **0.3816 monthly** against a best observed Sharpe of **+0.0396** → DSR = **0.0000** in every deciding cell. Multiple testing alone disqualified the cohort before costs or IC bars were applied.
- **The self-deception ceiling was measured directly** (§14): on a 53-signal closed library, pure best-of-N selection manufactures **t ≈ 3.6–4.0**. The project's own best full-sample mining result (t 3.27) **sits inside that noise band**. Allowing sign-flips (4 on record) pushes the ceiling to **t 6.16–6.58, Sharpe 1.44** — hence the standing rule that any t≥7 on this data is a defect, not alpha.

**⚠️ The critical open issue:** the survivors were deflated against 24 and 61 candidates. The search has since reached **179**. Neither insider nor fusion has been re-deflated against the final count, and both were already failing at the smaller counts. **Re-running the deflation at n=179 is a one-hour job and should be the first item of the next research session** — it will almost certainly move fusion's DSR from 0.10 to something indistinguishable from zero, which is itself a publishable finding.

## III.6 The three capstone research instruments

These landed 2026-07-26 and are intended as the paper's lead exhibits:

| Instrument | Result | Why it matters |
|---|---|---|
| **CZ-CALIB** | Rank correlation between published t-stat and house explore t-stat = **−0.544** | "Published t is a contrarian indicator" on this harness. Extraordinary if it holds up |
| **HARNESS-VALID** | 3/3 replication vs Ken French factors | The harness reproduces known results — so its nulls are credible |
| **INSTR-COST-REMEASURE-REJECTS** | The cost-killed cohort is **literally empty** | Rejections were informational, not frictional — the signals were dead, not just expensive |

---
# PART IV — HOW AEGIS ACTUALLY ALLOCATES CAPITAL TODAY

*This section answers directly: how many stocks, equal weight or return-weighted, and what happens at $1M.*

## IV.1 The headline

Every lane is seeded at **$100,000 flat notional** (10 lanes × $100k = $1M aggregate, but each lane is an independent, self-contained book). The four reference lanes hold **the entire 76-ticker universe simultaneously** — not a top-N screen. Weighting is **sleeve-mandated + HRP-within-equity** (or frozen equal-weight for the control).

**There is no volatility targeting that binds, no Kelly sizing, no leverage, and no AUM/capacity logic anywhere.** The whole system is exactly homogeneous of degree 1 in notional. **A $1M lane produces exactly 10× the P&L and byte-identical returns, Sharpe, and drawdown.**

## IV.2 The universe and the sleeves

`backend/data/paper_portfolios.yaml` — 76 names, frozen quarterly (`frozen_until: 2026-07-01`, **now a month overdue**):
- 65 equity = 11 sector ETFs + 6 broad ETFs + 48 individual stocks
- 7 bond ETFs, 4 alternatives

| | conservative | balanced | aggressive | balanced-ew-control |
|---|---|---|---|---|
| Notional | $100,000 | $100,000 | $100,000 | $100,000 |
| Equity/bond/alt/cash | 40/50/10/0 | 70/25/5/0 | 95/5/0/0 | 70/25/5/0 |
| Optimizer | `hrp` | `hrp` | `hrp` | `equal_weight` (frozen) |
| Max single name | **3%** | **5%** | **8%** | **5%** |
| Max sector | 25% | 30% | 40% | 30% |
| Drift trigger | 5% | 5% | 7% | 5% |
| Cadence | monthly | monthly | **weekly** | monthly |
| Crash overlay | >25% → cut equity 20% | >30% → cut 15% | >40% → cut 10% | >30% → cut 15% |
| Costs | 5bps txn + 1bps slip | same | same | same |
| Stop-loss / ATR | **none** | none | none | none |

**Equal-weight baselines — what the money actually looks like per name:**

| Lane | Per equity name | Per bond ETF | Per alt |
|---|---|---|---|
| conservative | 0.615% = **$615** | 7.143% = $7,143 | 2.50% = $2,500 |
| balanced / ew-control | 1.077% = **$1,077** | 3.571% = $3,571 | 1.25% = $1,250 |
| aggressive | 1.462% = **$1,462** | 0.714% = $714 | — |

**Two important structural facts:**
1. **HRP is equity-sleeve-only.** Bonds and alternatives are *always* equal-weighted. So even the "HRP" lanes are 1/7 per bond ETF and 1/4 per alt.
2. **The crash overlay has never fired.** `status: model_not_deployed, operational: false, armed: false` on all four lanes since inception, because `crash_model.pkl` is gitignored and was never baked into the Railway image.

**Live position counts (prod, 2026-08-02):** conservative **75**, balanced **75**, aggressive **71**, balanced-ew-control **76**. The EW control's live weights exactly match the arithmetic above, confirming it is genuinely frozen.

⚠️ **Caps are enforced only at rebalance, never continuously.** Conservative's top holding is currently 3.54% against a 3% cap — drift carries positions past the cap between the 28-day cadences.

## IV.3 The other six lanes

**mirror & conviction** — both seeded from the same 12-name real book (SOC, DKNG, NTLA, AARD, BHVN, HUBS, KYTX, PRCH, QUBT, AMSC, ABSI, SLDP), normalised to $100k at market-value weights on seed day.

| | mirror | conviction |
|---|---|---|
| Optimizer | `hrp` over 12 names | **`none`** |
| Cadence | monthly, 5% drift | **`never`** — only via logged decisions |
| Max single name | **25%** | ⚠️ **NOT IMPLEMENTED — no cap at all** |
| Stop-loss / overlay | none | none |

**conservative-atr** — byte-identical mandate to `conservative`; the only treatment difference is `exit_overlay: atr` (ATR period 14, Chandelier 3.0×, vol target 20%). ⚠️ **The vol-target half is inert**: at ~0.6% position sizes the cap would need realised vol >33× annualised to bind. **Only the ATR stop is live.**

**smallmid-quality** — 30 named stocks, **equal-weight at 1/30 = 3.333% = $3,333 each**, buy-and-hold, `rebalance_frequency: never`. Benchmark **IWM**, not SPY. `max_single_name: 0.10` is declared but never enforced (no rebalance path exists).

**tsmom-overlay / tsmom-6040-control** — **the only lane with real position sizing.** 4 assets (SPY, TLT, GLD, USO), 50% SPY core + 50% TSMOM sleeve, 12-1 momentum sign only, then **vol sizing: `min(0.10/σ₆₀, 1.5)`**, then equal-weight across active assets. Cash can go negative (margin). **Shorts allowed — the only lane with negative shares**, a declared paper-only exemption.

## IV.4 The rebalance path and the fill price

Four scheduler jobs: `pi_hourly_mtm` (16:30–19:30 ET, NAV write, all 10 lanes), `pi_daily_check` (16:30 ET, rebalance), `pi_weekly_aggressive` (Mon 09:00), `pi_congress_collect` (07:30).

**Fill price: SAME-DAY CLOSE. Signal date == fill date, signal price == fill price.** Zero implementation lag:
```
reference_engine.py:591-592   px = prices.get(ticker)        # ← the fill price
reference_engine.py:598       shares = (weight * net_notional) / px
```

**Live rebalance frequency is far lower than the config implies:** only **3 events in 55 days** on `balanced` — initialization (06-08), config change (06-10), monthly (07-08). Because on `conservative` the single-name cap (3%) is *below* the drift threshold (5%), and on `balanced` they are equal, **the drift trigger is effectively unreachable — the 28-day cadence is the real trigger.**

## IV.5 The cost model

**One model, uniform across all 10 lanes: 5 bps transaction + 1 bps slippage = 6 bps on dollars traded**, applied permanently to NAV at `net_notional = max(notional − total_cost, 0)`.

Live evidence: the 06-10 full-turnover rebalance on `balanced` cost **$28.42**; the 07-08 monthly cost **$4.62**.

**Not implemented in the lane path:** bid/ask spread model, commission, market impact, borrow cost on the TSMOM shorts, taxes. An Almgren-Chriss impact model *exists* at `backend/services/backtest.py:29-62` but **zero imports of it from the lane package**.

## IV.6 What breaks at $1M

**Mechanically: nothing.** Not implemented, by design and by omission:
- Round lots — not implemented (unrestricted fractional shares everywhere)
- Minimum position size / minimum trade notional — not implemented
- ADV / participation-rate limits — not implemented
- Market impact — not implemented
- Capacity ceiling or AUM-dependent cost curve — not implemented
- Liquidity screening — `adjust_weights_for_liquidity` exists with a $1M-ADV floor but **no lane calls it**, and it compares the stock's ADV to a constant so it wouldn't scale with book size anyway

**Economically: one thing breaks, and it breaks silently.** The 6 bps cost is defensible for a 76-ETF/large-cap reference lane at $100k. It is **not** defensible at $1M for the book lanes' micro-caps (SOC, AARD, KYTX, PRCH, QUBT, AMSC, ABSI, SLDP) or the SMQ names. A $1M mirror lane means ~$83k per name against a 25% cap — i.e. **$250k in a single micro-cap.** Nothing in the code would notice or object.

Cross-reference Part VI.2e: at $1M with a $5M-ADV name, the square-root law gives ~16 bps one-way impact and ~60–75 bps all-in round-trip, versus the 6 bps the model charges. **The cost model understates small-cap costs by roughly 10× at $1M scale.**

## IV.7 The concentration problem, measured

`docs/research/AI_PANEL_2026-08-01_ROUND16.md` — capture ratios vs SPY, 37 observations:

| Lane | Total % | Up-capture | Down-capture | Bull β | Bear β |
|---|---|---|---|---|---|
| **mirror** | −24.11 | **−0.98** | **1.58** | 1.07 | 1.05 |
| **conviction** | −11.77 | 0.25 | **1.44** | −0.32 | 0.87 |
| conservative-atr | +2.30 | 0.09 | −0.16 | 0.15 | 0.02 |

Mirror **loses money on 98% of SPY's up-days and captures 158% of its down-days** — negative convexity, the worst possible shape. The panel's adjudication: **concentration + expensive growth beta, not timing.** Mirror's beta is ~1.05–1.07 in both directions, so the SPY comparison **is** beta-fair for that lane — the −24pp is genuinely idiosyncratic loss from unhedged single-name concentration.

**In code, the concentration is structural:** conviction has **no cap at all**; mirror's 25% cap allows one name at a quarter of the book; SMQ's 10% cap is never enforced because the lane has no rebalance path.

## IV.8 Thirteen defects found in the allocation path

| # | Location | Issue |
|---|---|---|
| 1 | `reference_engine.py:506` vs `:545` | **Signals see day D's close; marks and fills use D−1's close.** Look-ahead in the lane's favour — worst on ATR stops, which by construction fire on adverse moves and are then filled at yesterday's *higher* price |
| 2 | `reference_engine.py:944` vs `nav.py:88-134` | **Live cash earns 0%; replay cash earns the T-bill rate.** ~4%/yr divergence wherever cash exists, violating the stated one-engine invariant |
| 3 | `scheduler.py:367` + `cache.py:92` | `cache_get` called with 1 of 2 required args → `TypeError` swallowed. The documented MTM self-skip **does not exist**; the cache key is never written anywhere |
| 4 | `book_management.py:221` | **conviction lane has zero position limits** — the lane the concentration finding is about |
| 5 | `scheduler.py:82-89` | `pi_daily_check` has no `day_of_week` → rebalance check fires Sat/Sun on stale Friday prices |
| 6 | `reference_engine.py:909` vs `scheduler.py:71` | Jobs in ET, NAV dates in UTC, no `TZ` in Dockerfile → the 19:30 ET slot writes tomorrow's date under EST |
| 7 | `scheduler.py:68-89` | MTM and daily-check both at 16:30 ET, unordered → NAV nondeterministically pre- or post-rebalance |
| 8 | `rebalancer.py:67-69` vs `reference_engine.py:594` | Unpriceable tickers booked at a **$100 placeholder** but cost nothing to trade |
| 9 | `db.py:149` | `open()` with no `encoding=` → on a cp1252 host the TSMOM YAML (contains `⚠`) falls back to a **raw-bytes hash**, producing a different config hash than prod. The hash is not reproducible off-Railway |
| 10 | `paper_portfolios.yaml` | Single-name cap ≤ drift threshold → drift trigger effectively unreachable |
| 11 | `paper_portfolios.yaml:16` | `frozen_until: 2026-07-01` — quarterly universe review **a month overdue** |
| 12 | `routers/portfolio_intelligence.py:87` | `/history?period=3M` returns empty while `period=ALL` returns 40 points over 55 days |
| 13 | `config.py:930` | Comment "NO live lane uses these yet" is stale — conservative-atr reads those values |

---
# PART V — THE ADVERSARIAL AUDIT

*Commissioned brief: "assume the results are wrong and hunt for the mechanism." This section is the answer. Findings are ranked; each states what would change if it is correct.*

⚠️ **Scope note:** the data-leakage sibling audit is now COMPLETE and appears as Part V-B immediately after this section. It contains the most consequential findings in this document.

---

## 🔴 F1 — CRITICAL: the placebo gate that closed the search phase is inflated by ≈√5. Both firings are statistical artifacts.

**What is claimed:** §30 and §31 declared NO CONCLUSION on pooled placebo `t = −3.17` and `−3.02` against a frozen bar of `|t| < 2.0`. **Those two firings closed the 13D family as "unmeasurable" and terminated the search phase at 179 candidates.**

**What the code does.** `Aegis module/aegis_brain/factory/event_harvest.py:247-272` pools all five random seeds into one frame and computes a single cluster-robust t clustered on **entry month**:

```python
allrows = pd.concat(pooled, ignore_index=True)
stat = de.clustered_t(allrows["diff_net"], allrows["entry_month"].astype(str))
```

Stacking 5 seeds multiplies N by 5. Because `redraw_filing_dates` scatters each permno's redraws into **five different months**, the entry-month cluster does **not** group a permno's five draws together — so the estimator treats five draws of the same permno as five independent observations.

**The arithmetic is decisive:**

| | Per-seed t values | Mean | Mean × √5 | **Reported pooled** | Ratio |
|---|---|---|---|---|---|
| §30 | −2.48, −1.23, −1.95, −0.31, −1.42 | −1.478 | **−3.305** | **−3.17** | 0.96 |
| §31 | −1.77, −1.73, −2.77, +0.52, −0.91 | −1.332 | **−2.978** | **−3.02** | 1.01 |

The pooled statistic *is* the per-seed mean scaled by √n_seeds, to within 4% and 1%. **That is the exact signature of treating correlated replicates as independent.**

**Why it invalidates.** The five seeds share the *identical permno cohort*. §30 itself attributes 72% of the placebo effect to "a gross cohort drag of −24.8 bps/mo that the matched control does not remove" — a component common to all five seeds *by construction* cannot be a source of independent information about itself.

### ⚠️ CORRECTION (verified by direct computation, 2026-08-02) — the agent's conclusion does NOT hold

The per-seed values were recovered from `data/factory/trial_13dg_harvest.json` and `trial_13dg_harvest2.json` and the arithmetic was re-run. **The √5 mechanism is CONFIRMED** — but the claim that "the gate PASSES" is **wrong**, and the direction of the error is the opposite of what was reported.

| Trial | mean | mean×√5 | reported pooled | ratio | median\|t\| | n>\|2\| | **seed-level t** |
|---|---:|---:|---:|---:|---:|---:|---:|
| §30 HARVEST | −1.478 | −3.305 | **−3.17** | 0.959 | 1.42 | 1 of 5 | **−4.06** |
| §31 HARVEST2 | −1.332 | −2.978 | **−3.02** | 1.014 | 1.73 | 1 of 5 | **−2.43** |

**The verdict is specification-dependent:**

| Reading | §30 | §31 |
|---|---|---|
| Pooled rows, as run | −3.17 → **FAIL** | −3.02 → **FAIL** |
| **Seed-level t** (mean across seeds ÷ its own SE) | **−4.06 → FAIL** | **−2.43 → FAIL** |
| Median seed \|t\| | 1.42 → PASS | 1.73 → PASS |

**Why the agent was wrong:** it read the median seed and stopped. But the natural per-seed test — *"is the mean placebo effect across seeds different from zero?"* — gives **t = −4.06 for §30, which is MORE extreme than the pooled statistic it was supposed to correct.** The five seeds *agree* with each other (tight dispersion), so the mean is precisely estimated. Consistent agreement across random-date draws is evidence *for* a cohort drag, not against it.

**What survives, and it is still a real finding:** the pooled statistic is mechanically the per-seed mean scaled by √5 (ratios 0.959 and 1.014), so the row-level pooling **is** misspecified. But **the pooling rule was never pre-registered**, and the three defensible readings do not agree. **The search phase therefore closed on an arbitrary specification choice — not on a demonstrated artifact.**

That is a weaker claim than "reopen the family," and an honest one. **Do not reopen the 13D family on this basis.** The correct remedy is to pre-register the pooling rule and the seed count *before* any re-run, and to note in the paper that the terminal verdict rested on an unregistered choice.

**The bar is also mechanically unreachable by design:** pooled precision rises with seed count, so **adding seeds makes the gate harder to pass regardless of the truth.** Nothing documents how 5 was chosen — it was inherited from an earlier post-hoc diagnostic.

**Remedy:** (1) re-read both gates on the **per-seed distribution** (e.g. "fires if ≥3 of 5 seeds exceed |2|"), or pool the *seed-level t's* as 5 draws rather than 5× the rows; (2) if pooling rows, cluster on **permno**, the axis where dependence actually lives; (3) freeze the seed count and state the pooling rule in the trial doc before re-running.

> **This is the single highest-value item in the audit. It may reopen an entire closed family and un-terminate the search phase.**

---

## 🔴 F2 — CRITICAL: the placebo does not preserve the temporal structure of the real events

`event_harvest.py:228-242` redraws filing dates **uniformly at random** across the explore window.

Real 13D filings are strongly non-uniform in calendar time — activism clusters after price declines and in waves (2007-08, 2020). A uniform redraw gives the placebo arm a *different calendar-month marginal* from the real arm, so the placebo/real difference confounds cohort drag with **calendar composition**. It also destroys within-permno event clustering, which real filings exhibit.

The placebo therefore answers *"what does this pipeline report on a cohort observed at uniformly random times"* — not *"what does it report when timing information alone is destroyed,"* which is the question the gate was written to ask.

**Combined with F1, the entire −20 to −25 bps/mo "cohort drag" attribution is unestablished.**

**Remedy:** replace with a **permutation placebo** (shuffle real event dates *across* permnos, preserving the calendar marginal exactly) or a **circular block shift** of each permno's date sequence.

---

## 🔴 F3 — CRITICAL: the DSR/PBO gate deflates against 18 trials, not 179 — and has never been run on a single survivor

Live registry (`rule_experiments`):
- `cumulative_trials: 18`
- `verdict_counts: {"adopted": 18}` — **zero rejections**
- **Every one of the 18 rows has `dsr: null, pbo: null, observed_sharpe: null, n_obs: null`**

`experiment_registry.py:143-157` is the gate: `n_trials = cumulative_trial_count(db) + batch_trials`. That reads **18**. The programme's own documented count is **179**.

Three compounding failures:
1. `expected_max_sharpe(18)` vs `expected_max_sharpe(179)` differ by ~30% in the null bar. **The gate is systematically too lenient by the ratio of the counts.**
2. **The 179 counter exists only as hand-incremented prose in markdown**, was reconciled retroactively at least once, and is not machine-readable. The module's own ledger has 52 rows carrying no verdict, no result, no n.
3. The **83 completed lab cycles**, each of which logs a hypothesis, are counted **nowhere**.

**And the canon violation:** CANON §6 states *"a project whose registry shows only adoptions is lying to itself."* **The registry shows only adoptions — 18 of 18.** The rejections live in prose. The project's own constitution is violated by its own registry.

**Remedy:** make the counter an artifact, not prose — one append-only row per candidate arm with `{id, registered_at, verdict, primary_stat, n_obs}`; back-fill all 179; have `cumulative_trial_count()` read it. **Then actually run `evaluate_candidate` on gp-small, insider, fusion and TSMOM-XA at n=179+ and publish the four DSRs.** Right now the paper's central methodological claim — "we deflate against the cumulative count" — is **described but not executed.**

---

## 🟠 F4 — HIGH: deflation is applied only to rejections, never to the one PASS

Rejections carry deflation: §13 "DSR 0.0003 at N=140"; §27 "DSR 0.0000 at n=173"; §14's zero-skill ceiling t 3.6–4.0.

The programme's **only event-family PASS** — §29, candidates 175–177 — reports a raw clustered **t 4.75 with no DSR, no expected-max-under-null, and no deflation against the 177-candidate count.**

**An asymmetric gate manufactures the shape of the result.** Every candidate that failed had to clear a multiple-testing bar; the one that passed did not. §14's own calibration says a 53-signal library tops out at t ≈ 3.6–4.0 under zero skill; 177 candidates implies a higher bar still, and **4.75 is not obviously above it.**

Related: §22's named cost-killed exception `rec_mom` (t 2.64, best of 160) sits **below** the project's own zero-skill maximum for a *53*-signal library, yet is elevated to a positive named finding.

---

## 🟠 F5 — HIGH: there is no confirm-window touch counter

The explore/confirm wall is stated repeatedly as protocol — *"one-shot confirm, reruns forbidden"*, *"held out and readable exactly once per graduate."* **Grep across all three repos returns zero occurrences of `CONFIRM_START`, `confirm_window`, or any counter.** The `pre-register-trial` skill has no confirm-budget field.

Meanwhile the confirm window has demonstrably been read **at least 6 times** (§13 conc_low, §15 JM1, §18 JM2, §21 COND-VT, §23 resid-mom, TSMOM-XA), against a window the project's own docs say **"holds ~1–2 regime events."**

**Six reads against an effective sample of 1–2 independent events is a 6-way multiple comparison.** §18 is the sharpest case: JM2 was a post-hoc repair of JM1 re-tested on the same confirm window — the classic sin. The project caught it and pre-declared zero evidential weight on the explore leg, which is admirable, but **the confirm leg was still spent a second time on the same mechanism family.**

---

## 🟠 F6 — HIGH: 55 days × 10 lanes has essentially zero statistical content

Computed from the live record (37 daily observations, 18 up / 19 down days):

| Quantity | Value |
|---|---|
| Minimum detectable effect at 80% power | **annualised Sharpe 7.31** |
| **Power to detect a true annualised Sharpe of 1.0** | **5.7%** (a coin flip is 5%) |
| Days to detect Sharpe 1.0 at 80% power | 1,978 (**7.8 years**) |
| Days to detect Sharpe 0.5 at 80% power | 7,912 (**31.4 years**) |
| **P(≥1 of 10 independent lanes "significant" at 5%)** | **40.1%** |

**The multiple-lane problem is real and unmanaged. Ten lanes is ten shots.** The observed spread (+3.59% to −22.44%) is entirely consistent with the null across 37 days.

**Three concrete reporting hazards:**
- `aegis_verified_state` presents one header `inception_date: 2026-06-08, age_days: 55` over a table where lanes have **different inceptions** (tsmom pair ~5 days, SMQ ~10 days). `tsmom-overlay +0.102%` and `mirror −22.435%` are printed in one column and are not comparable numbers.
- `comparator.py:108-110` computes `ann_return = (1+total_return)**(1/n_years)` with `n_years = 37/252 = 0.147` — **a 6.8th-power extrapolation of 37 days.** Mirror's −22% annualises to ≈ **−83%**. No minimum-window guard.
- `comparator.py:143` gates beta, tracking error, and information ratio behind `if len(aligned) >= 60`. **At 37 obs all three are silently `None`** — the one guardrail that would make the SPY comparison fair does not run on the actual live record.

---

## 🟠 F7 — HIGH: rejects declared from low power — absence of evidence read as evidence of absence

| § | Claim | Stat | Reconstructed 95% CI | Problem |
|---|---|---|---|---|
| §16 | FDA daily drift "closed at BOTH resolutions" | +2.1%, t 1.45 | **[−0.74%, +4.94%]** | A +4% 20-day drift — very large and tradeable — is inside the interval |
| §11 | FDA monthly REJECT | −30.1 bps/mo, t −0.89 | **[−96, +36] bps/mo** | +30 bps/mo (≈+3.7%/yr) is inside |
| §13 | conc_low "KILL" | −5.5 bps/mo, t −0.20 | **[−59, +49] bps/mo** | The explore estimate sits *inside* the confirm CI. **The confirm did not contradict explore — it failed to re-detect.** The IC leg survived at t 2.6 |
| §26 | "there was nothing to execute" | best zero-cost net t +1.16 | — | t=1.16 is an unresolved sign, not a demonstrated zero |

**8 of 31 sections state no sample size at all.** §3 declares LPPLS "refuted" with neither a statistic nor an n.

**Remedy:** two lines in the trial template fix most of this — (a) compute and record the **MDE before the run**, next to the bar; (b) report the **CI, not just the t**, and use *"did not clear the bar; the design could not have detected effects below X"* rather than *"there is nothing there."* A bar-miss at t 1.45 and a bar-miss at t 0.10 are different findings and currently read identically.

---

## 🟠 F8 — HIGH: pre-registered decision rules fire on noise

**TRIAL-001** — "adopt if HRP leads control net Sharpe by ≥0.30 / revert if trails by ≥0.30", 12-month window, decision date **2027-06-10**.

At 252 daily observations, SE(annualised Sharpe) ≈ 1.00. For the *difference* between two lanes with correlation ρ:

| ρ(HRP, EW-control) | SE(diff) | **P(rule fires under the null of zero difference)** |
|---|---|---|
| 0.90 | 0.447 | **50.2%** |
| **0.95** | 0.316 | **34.3%** |
| 0.98 | 0.200 | 13.4% |

**Two variants of the same balanced mandate will run ρ ≈ 0.95–0.98, so the rule fires by chance 13–34% of the time — in either direction.** That is a coin-weighted coin, pre-registered.

**TSMOM-XA** — primary metric is "overlay maxDD vs control maxDD, shallower by ≥3pp." Max drawdown over 24 months is **a single order statistic of one path**, n_effective = 1 drawdown episode. No sampling distribution is specified.

**SMQ** — at 504 obs, MDE at 80% power ≈ annualised Sharpe **1.98**. The trial cannot detect anything smaller, and its own prior is "DSR ~0.10 and FF6 alpha negative."

**Pre-registration is doing its job (tamper-evidence) but is being asked to substitute for power.** A pre-registered rule with a 34% false-fire rate is not more reliable than a post-hoc one — it is just harder to argue with later.

---

## 🟡 F9–F15 — MEDIUM and LOW

**F9 — Two contradictory deflation policies in the codebase.** `experiment_registry.py:8-13` states the rule: deflate against the CUMULATIVE count, because "a loop that re-deflates only per-batch slowly becomes an overfitting machine." `signal_optimizer.py:210` does exactly that: `n_trials = len(results)` — no registry read. **The one production path that recommends a config change deflates per-batch, against the very failure mode the registry docstring names.**

**F10 — The purged-CV protocol in METHODOLOGY §1.4 is not the protocol that runs.** `engine/autoresearch/aegis_prepare.py:117` calls `PurgedKFold(..., horizon_days=h_days)` — **not a constructor parameter**; the call raises `TypeError`. Even if fixed, `cv.split(X_valid)` passes no `eval_times`, and `purged_cv.py:73` documents that this **silently degrades to plain contiguous k-fold with no purging**. Separately, `feature_selection.py:96` uses `LogisticRegressionCV(cv=5)` → `StratifiedKFold`, interleaved across the whole timeline, on 63–252-day overlapping labels, **called on the full unsplit matrix before any split exists.**
> **Every AUC/Brier the methodology section reports as walk-forward is produced by a weaker protocol than the one described.** `METHODOLOGY.md:48-53` should not be cited in the paper until the code matches it. The `eval_times=None` path should **raise**, not degrade — this is CANON §8's own failure mode sitting inside the validation layer.

**F11 — IC t-stats on overlapping windows, uncorrected, feeding live trial primary metrics.** `factor_ic.py:88` computes `t = ir·√n` with no Newey-West adjustment (the docstring is honest: "treat as an upper bound"). But this feeds the registered primary metric for TRIAL-ARK-IC, TRIAL-CONGRESS-IC and TRIAL-CMP-INSIDER-IC — *"forward rank-IC at 21/63/126d"*, **overlapping by construction**. Nothing downstream re-labels it, and the adopt thresholds are stated against the uncorrected statistic. **Fix before the first decision date (2027-01-11), not after.**

**F12 — §29's book stage keeps FAIL where the project's own logic requires NO CONCLUSION.** §30 states the principle: *"A number cannot be scored against a bar written at zero when its own null sits three standard errors below zero."* The book stage's own placebo found exactly that, and the section concedes it *"would have failed even if the drift were fully harvestable"* — yet retains FAIL because the bar was frozen. **The FAIL propagated:** §29's PENDING prediction leg was retired as a **HIT** on its strength. A stage that could not have answered either way cannot confirm a prediction. **Re-file as NO CONCLUSION and re-open the prediction leg — this costs the project a scored hit, which is exactly why it is credible to do.**

**F13 — The capture diagnostic is read at noise resolution, though the diagnosis is right.** Up-capture on **18 up-days**, down-capture on **19 down-days**. Mirror's −0.98 is a ratio of two small sums over 18 observations with enormous sampling error. The doc labels it descriptive, then treats it as a structural property and derives a product decision plus a leverage refusal from it. **The conclusion is very likely correct on priors; the evidence presented does not establish it.** Ground the concentration-cap decision in the *holdings* (position weights, HHI, single-name max) — measurable at n=1 — not an 18-day capture ratio.

**F14 — Post-hoc thresholds derived from observed outcomes, then applied forward.** §24's "turnover above ~0.15/month should be expected to die net" was read off the same 19 post-hoc results it summarises, with no holdout, then proposed as a **gate on future candidates**. §14's "t≥7 = bug" alarm was subsequently exceeded without triggering (§26 t 11.29 and 10.64; §28 t 8.50; §29 t 7.74) and effectively retired without being restated.

**F15 — Bookkeeping.** 83 lab cycles counted nowhere. `walk_forward.py:138` uses an **i.i.d.** bootstrap for the AUC CI, two lines from `metrics.brier_with_ci` which correctly uses a **block** bootstrap on the same overlapping labels — AUC intervals are too narrow. `tearsheet.py:104` same issue for Sharpe/Sortino. `overfitting.py:418` defaults `CombinatorialPurgedCV(embargo_td=0)` — a caller who forgets gets an unembargoed CPCV silently.

---

## V.2 What the project gets RIGHT

This matters as much as the findings. These practices are unusual and must survive any remediation.

**1. `gated_run` — compute-order as tamper-evidence.** `real_fn` is *not called* — the real number does not exist in the process — unless the placebo passes. **This is the only mechanism found in any of the three repos that makes "we didn't peek" verifiable rather than asserted.** The pooling statistic inside it is wrong (F1); the architecture around it is better than most published finance research. **Fix the statistic, keep the pattern.**

**2. §20 — a pre-registered bar PASSED and the result was thrown away anyway.** Treatment −5.95% (t −7.06); control −6.79% (t −11.33). The control beat the treatment, so the passing headline was discarded and the family filed UNADJUDICATED rather than closed. Almost nobody does this.

**3. Predictions registered and scored, including the misses, in the same document.** *"Four stage-level predictions on this family, four misses — and this one also named the wrong mechanism for the previous miss."* §31 retro-annotates a refutation of §30's own explanation. **A research file that records its author being wrong four times in a row about the same axis is a file you can trust on the fifth.**

**4. `effective_number_of_trials` is reported and structurally forbidden from gating.** N_eff falls back to `float(n_streams)` on *every* non-ok status, "so that even a caller that ignored this rule could not be made more lenient by a degenerate estimate." **Building the loosening direction to be impossible, rather than trusting the caller, is exactly right.**

**5. `metrics.brier_with_ci` is the reference implementation** — circular block bootstrap, auto block size, `n_positive` reported, `low_event_warning` below 10 positives, and METHODOLOGY explains *why* i.i.d. would be wrong. Every other CI in the codebase should route through it.

**6. `train_severity_model.py` is textbook** — `train_end = block[0] − (PURGE + EMBARGO)`, expanding window, **two** baselines fit inside each fold, gate frozen before the first fit, result 0 of 6 cells.

**7. CANON §2 refuses to let the overfitting gate launder a biased universe** — *"the DSR/PBO gate cannot save it… that is exactly how vol-managed momentum printed a false PASS."* **Knowing which failure your guard does not cover, and having the receipt for the time it didn't, is rarer than having the guard.**

**8. Harness validation against external ground truth** — vs Ken French: EW market 0.927, SMB 0.778, UMD 0.645, all passing pre-set bars. **This is what lets the graveyard be read as a finding rather than as a broken pipeline.**

**9. Voided runs published with their numbers** — §23's defective run was caught by a spec test written *after* it, the void numbers are recorded rather than deleted, and the section points out the void run made the signal look **worse**, pre-empting the obvious suspicion.

**10. The negative-results file exists, is 1,651 lines, and is the primary deliverable.** A programme that has concluded its honest output is a paper about 179 failures, and kept the receipts for each, is in a far better epistemic position than one reporting four survivors.

---

## V.3 Recommended order of remediation

1. **F1 + F2** — re-specify the placebo and re-read both gates per-seed. **May un-close the 13D family and the search phase.** Nothing else changes as many downstream conclusions.
2. **F3** — make the 179 counter a machine artifact; run `evaluate_candidate` on the four survivors at the true count; publish the DSRs.
3. **F12** — re-file the book stage as NO CONCLUSION; re-open the §29 prediction leg.
4. **F6 + F8** — per-lane `n_obs`/inception everywhere; suppress annualisation below 126 obs; add `P(fire | H0)` and MDE to every registered decision rule. **TRIAL-001 is urgent — it decides 2027-06-10.**
5. **F5** — confirm-read counter with a hard budget.
6. **F4, F7** — apply the hurdle to acceptances; add pre-run MDE and post-run CIs to the trial template.
7. **F9, F10, F11, F15** — code fixes. F10's silent k-fold degradation should `raise`.
8. **Re-run the terminated leakage audit.**

---
# PART V-B — THE DATA & LEAKAGE AUDIT

*This audit was terminated mid-flight by an API limit and re-completed later. It is the most consequential section in this document: it contains two empirically confirmed fabrications in live production data, and one systematic look-ahead that plausibly explains the project's headline model numbers.*

**Summary: a live, confirmed fabrication exists in the one evidence path the project says it trusts (forward-IC on PIT snapshots). Several of the project's own anti-leak guards are tautological and cannot fail.**

---

## 🔴 L1 — CRITICAL, CONFIRMED: the insider forward-IC clocks have accrued 100% fabricated zeros

**This changes the survivor list from four to three.**

Queried directly against `backend/data/aegis_pi.db`:

```
insider_opp:  6 as_of dates × 12 tickers = 72 observations. ALL 72 are exactly 0.0.
              distinct values per date = 1. Every payload: n_distinct_buyers: 0.
insider_cmp:  every payload has n_live_opportunistic: 0, n_live_routine: 0,
              n_live_unclassifiable: 0  →  the live SEC leg returns NOTHING.
              Its only nonzero values (BHVN 3.0, DKNG 1.0) come from
              n_panel_buys with panel_end: "2026-03-31" — a FROZEN artifact.
```

**The mechanism** — `backend/services/insider_form4.py:164-178`:
```python
empty = {..., "buys": [], "n_buys": 0, "total_buy_value": 0.0}
cik = cik_for(ticker)
if not cik: return empty
except Exception as e: logger.warning(...); return empty
```
That `empty` flows to `compute_opportunistic_buy_score` → `0.0` → and is **written into the point-in-time store as a genuine observation** by `pit_score_collector.py:66-67`.

**Why this is a fetch failure, not a real absence:** the book universe is AARD, ABSI, AMSC, BHVN, KYTX, NTLA, PRCH, QUBT, SLDP, SOC, DKNG, HUBS — micro/small-cap biotech and speculative names, where open-market insider buying is *most* common. **The frozen CMP panel proves insiders did buy** (BHVN: 3 opportunistic buyers, 5 panel buys). The live leg sees zero for all 12, every week.

**This is NEGATIVE_RESULTS §5 — the 2026-06-17 SEC-403 incident — recurring undetected.**

**The health flag structurally cannot see it** — `backend/services/cmp_insider.py:146`:
```python
degraded = (not artifact) or panel_end is None or gap_days > STALE_GAP_DAYS  # 210
```
It only checks *artifact staleness* (124d < 210d → `degraded: false`). **It never checks whether the live fetch returned anything. The collector self-reports healthy while its live leg is 100% empty.**

**Consequences:**
- **TRIAL-INSIDER-IC and TRIAL-CMP-INSIDER-IC (decision date 2027-07-21) have accrued zero information since 2026-06-16.**
- **"insider" is listed as one of four surviving candidates. It is a constant.**
- `insider_cmp` will return the *identical* value at every future `as_of` **forever**, because its only live input is dead and its panel is frozen at 2026-03-31.

**Verify:** run the SQL above on prod, then on Railway:
`python -c "from backend.services.insider_form4 import fetch_open_market_buys; print(fetch_open_market_buys('BHVN'))"` — expect `n_buys: 0` while EDGAR shows Form 4s.

**Fix:** (a) `pit_score_collector` must **not write** when scoring raises or the fetch returns nothing — write a null/absent marker or skip; **a fabricated 0.0 is worse than a gap**. (b) `degraded` must include `live_fetch_ok`. (c) add a cross-sectional canary: N consecutive all-identical cross-sections → alarm.

---

## 🔴 L2 — CRITICAL, REPRODUCED: a dead signal produces `status: "scored"` with a fabricated quantile spread

`engine/validation/factor_ic.py:135`:
```python
q = pd.qcut(g[factor_col].rank(method="first"), n_quantiles, labels=False)
```

`ic_by_date` guards degenerate cross-sections (`:74-75`). **`quantile_return_spread` does not.** On an all-tied factor, `rank(method="first")` breaks ties by **row order** — which is alphabetical ticker order, since `book_universe()` returns `sorted(...)`. **So qcut produces five clean buckets from the alphabet.**

Reproduced against the exact shape of the dead insider clock (12 tickers × 5 dates, factor ≡ 0.0):
```
"status": "scored",  "n_rows": 60,  "n_dates": 5,  "data_grade": "directional",
"ic": {"n_periods": 0, "reason": "no valid IC periods"},
"quantiles": {"available": true, "top_minus_bottom": 0.00096, ...}
```

**A +9.6 bp factor spread manufactured out of a constant.**

Also: `forward_ic.py:130-131` overwrites `n_dates` with the raw-panel count *after* `analyze_factor` — so the receipt claims 5 dates when **0 contributed to the IC**.

Even with a *healthy* sparse signal this bites: insider scores are 0 for most names by nature, so **most of the quantile spread is alphabetical noise**. Both `forward_ic.py:127` (every trial) and `validate_momentum.py:122` consume this function.

**Fix:** skip any date where `nunique() < n_quantiles`; return `available: False, reason: "degenerate cross-section"`. Gate `score_forward_ic` on `ic["n_periods"]`, not raw row count. **Every factor result the bench has ever produced on a sparse signal needs re-reading.**

---

## 🔴 L3 — CRITICAL: FRED macro features are aligned to the reference date, not the release date

**~1–5 months of look-ahead in every crash-model feature.**

`engine/training/features.py:286`:
```python
s = pd.Series(series).astype(float); s.index = pd.to_datetime(s.index)
s = s.reindex(df.index).ffill()      # ← reference-date index, no publication lag
```
Fed by `data_fetcher.py:451` — `fred.get_series(series_id)` with **no `realtime_start`/`realtime_end`**, i.e. the latest-revised vintage.

`fredapi` returns series indexed by the *reference period*. **UNRATE for September 2008 is indexed `2008-09-01` but published `2008-10-03`.** After `reindex().ffill()`, the model sees September's unemployment rate on **September 2nd**.

Of the 24 series in `config.py:137-167`, ~14 are lagged-publication monthly/quarterly, each generating 4 features ≈ **56 leaky features**:

| Series | Look-ahead | Why it's worst |
|---|---|---|
| `RECPROUSM156N` | ~2 months + **two-sided** | Chauvet-Piger *smoothed* recession probability uses data from **both sides of t by construction. This is not a feature, it is a soft label** |
| `BOGZ1FL663067003Q` | ~5 months | Z.1 flow-of-funds, published ~2.5mo after quarter *end*, indexed at quarter *start* |
| `DRTSCILM`/`DRTSCLCC` | ~2 months | SLOOS quarterly survey |
| `UNRATE, CPIAUCSL, INDPRO, MANEMP, BUSLOANS, TOTALSL, UMCSENT, FEDFUNDS, USSLIND` | 2–6 weeks | Plus retroactive seasonal-factor re-estimation |

**Why every prior audit missed this:** `docs/DATA_OPTIONS.md:49-70` and backlog B14 audit the **revision** axis and correctly grade it "mild." **Nobody audited the alignment axis, which is much larger.** And `data_integrity.py`'s `SOURCE_GUARANTEES` (`:81-107`) registers yfinance/fmp/polygon/finnhub/sharadar — **there is no `fred` entry and no `point_in_time_macro` field**, so macro leakage falls outside the grading regime entirely.

> **This plausibly explains the headline numbers in `CLAUDE.md` — "Walk-forward AUC ≥ 0.70" and especially "Brier ≤ 0.05" (climatology ~0.12). A Brier of 0.05 is not a believable out-of-sample number on ~7 crash events.**

**Verify:** rebuild the feature matrix with every monthly series `.shift(freq='45D')` and quarterly `.shift(freq='90D')`; re-run walk-forward. **If AUC collapses toward 0.5, the leak was the result.** Cheaper first cut: drop `fred_recession_prob*` alone and re-measure.

**Fix:** per-series `publication_lag_days` map in `config.py`, shifted before `reindex`. For sizing-grade work, pull ALFRED first-release vintages. Register `fred` in `SOURCE_GUARANTEES` with `point_in_time_macro=False`.

**Note the irony:** the project already solved exactly this problem for Fama-French — `factor_model.py:44-92` pins the vintage behind a sha256 gate with a test. **Do that for FRED.**

---

## 🔴 L4 — CRITICAL: the anti-leak assertions are tautological and cannot fail

`market_data_wrapper.py:54-60, 72-79`:
```python
sliced = self._prices.loc[:ts]
assert sliced.index.max() <= ts, "Look-ahead leakage: ..."
```

**`.loc[:ts]` on a sorted DatetimeIndex cannot return an index value `> ts`. Verified: the assertion can never fire.** Same for `fred_as_of` (`:76`) and `crash_features_as_of` (`:111`).

Worse: `fred_as_of` asserts on the **reference-date** index while serving **latest-revised** values — **so the codebase's most rigorous-looking leakage guard checks the one axis that is safe by construction, and is blind to both real leaks in L3.**

This is *false assurance*: it makes the replay path read as validated. **Replace with assertions that can fail** — assert the series' release date `<= ts`, and assert the vintage is a first release.

---

## 🟠 L5 — HIGH: "multi-factor" is a 2-factor model with a constant third leg

`multifactor.py:72`: missing → `0.0`, indistinguishable from a real 0.0. `_zscore` returns all-zeros when `sd == 0`, so **a dead component silently contributes nothing while still consuming its 1/3 weight** (`den` is always 3).

**Confirmed live, 2026-08-02:** every payload shows `{"insider": 0.0, "momentum": 18.2, "revisions": -4.0}`. **The composite is `(z(momentum) + z(revisions) + 0)/3` — a 2-factor model reported as 3-factor, with magnitude deflated by 1/3.**

Also `get_latest_observable` (`db.py:471-487`) has **no staleness bound** — a component frozen months ago reads as current.

---

## 🟠 L6 — HIGH: partial price-fetch failure marks positions at entry price

`reference_engine.py:944-947`:
```python
marks[r["ticker"]] = px if (px is not None and px > 0) else r["cost_basis"]
```

Total failure is correctly guarded. **Partial failure is not — and the fallback is cost_basis, not last-known price.** A name bought at 100 now trading at 60, whose feed fails, is marked at **100**.

**The failure mode correlates with the event:** halts, delistings and ticker changes cluster with bad news. **NAV is biased upward exactly when it matters most.**

**Verify:** `SELECT` positions where `mark == cost_basis` on any NAV date after inception.

---

## 🟠 L7 — HIGH: survivorship is worse than the documentation says

Two things the existing write-ups understate:

1. **The universe contains post-hoc winners, not just survivors.** `paper_portfolios.yaml` has an `emerging_tech`/`quantum_cleantech` block — **PLTR, MSTR, COIN, RKLB, RGTI, IONQ, SLDP**. These were selected *because* they became famous by 2026. **That is selection on the outcome — a strictly stronger bias than survivorship.** A replay over 2021-2025 on that universe is not measuring a strategy.
2. **Delisted names can inject a different company.** Of 20 known S&P deaths: 15 GONE, **4 REUSED** (CFC, JAVA, EMC, RE return a *different* company's history on the recycled symbol), 1 usable. **Any future attempt to "just add the delisted names" injects wrong-company prices — worse than dropping them.** Nothing in the live code guards against symbol reuse.

`config.py:859` also still contains **PXD** (acquired by Exxon, May 2024) and **SQ** (ticker changed) — the list is already stale.

---

## 🔴 L8a — CRITICAL, NEWLY FOUND IN THIS SESSION: `smartgrowth_pick` is also a constant

**Not found by the audit agent — surfaced by direct verification.** `smartgrowth_pick` has **40 observations and exactly 1 distinct value (0.1), on every one of its 4 collection dates.** The cross-section has zero variation.

That is **TRIAL-SMARTGROWTH (registry id 9, pre-registered 2026-07-12, earliest decision 2027-01-12)** — the trial built around Murat's own tech/forecast/real-investor thesis. **It has accrued zero information since inception, for the same class of reason as the insider clocks.**

**Two of the project's live forward clocks are measuring nothing, and neither was detected by any health surface.**

---

## 🟡 L8b — MEDIUM (agent claim CORRECTED): the IC panel is pseudo-replicated

⚠️ **The audit agent claimed `quality_score` has "one distinct value for all 12 tickers across all 5 dates." Direct verification shows that is wrong** — `quality_score` has **7 distinct values in every cross-section**, stable across all 5 dates, and `pead_score` has 8–9. Those two signals have genuine cross-sectional variation and are *not* dead.

**What does hold:** `insider_cmp`'s cross-section is identical (3 distinct values) on all 3 of its dates — frozen, because its only live input is dead and its panel ends 2026-03-31.

**And the overlap problem is real regardless of which signals are alive.** `_forward_return` pairs each date with a 21-day forward return, so consecutive weekly dates share **~75% of their return window**.

`ic_summary` then computes `t = (mean_ic/std_ic)·√n` treating those as **n independent periods**. With a frozen factor and overlapping returns, **n is effectively 1.** The module docstring acknowledges overlap and says "sample on non-overlapping windows" — **nothing enforces it.** This inflates every t-stat the forward-IC bench produces.

## 🟡 L9 — MEDIUM: backfill is a silent no-op

Live `as_of` dates show a **21-day gap** despite a 5-day throttle on a daily scheduler.

`pit_score_collector.py:44-49` compares `date(as_of) - date(MAX(as_of))`. **For a backfill the delta is negative, which is `< timedelta(days=5)` → returns `{"status": "throttled"}`.** Verified: `date(2026,6,1) - date(2026,7,28) = -57 days` → throttled. **A repair run does nothing and reports a status that reads like normal cadence.**

Worse: `fetch_open_market_buys` hardcodes `cutoff = date.today() - lookback_days` and **ignores `as_of` entirely.** If the throttle were bypassed, a backfill to `as_of=2026-06-01` would fetch *today's* window and stamp it as a June observation — **a direct look-ahead injection into the PIT store.**

## 🟡 L10 — MEDIUM: `run_reference_check(as_of_date=...)` silently ignores its as-of parameter

`reference_engine.py:274-300` accepts `as_of_date`, but `_get_current_prices` and `_get_price_panel` both hardcode `date.today()` — **including in the cache key.** Only tests pass a past date today, so no research result is currently affected — but **any future replay wiring through this entry point leaks completely.**

---

## V-B.2 What the leakage audit found to be genuinely RIGHT

- **`backend/db.py`'s PIT contract is correctly designed** — `observed_at <= cutoff`, never overwrites, revisions preserved. `pit_collectors.py:126` correctly stamps 13F `observed_at = filing_date` (the real 45-day lag).
- **`insider_form4.py:197` stamps filing_date, not transaction date.** `estimate_revisions.py:272` filters correctly. Congress uses `disclosureDate`, never `transactionDate`.
- **Fama-French vintage is genuinely pinned** behind a sha256 gate with a test — **the right answer to exactly the problem L3 describes for FRED.**
- **`compute_fragility_index` now takes `as_of_ts` and slices all inputs** — `LOOKAHEAD_AUDIT.md §2` / backlog B5 was actually fixed, and that audit's claims still hold.
- **TSMOM signal alignment is clean** — signal at prior month-end, vol window ending at the signal date, execution after.
- **`mark_lane_to_market` refuses to write a NAV row on total price failure** — correct, and the reason L6 is "high" not "critical."

---

## V-B.3 Order of attack

1. **Today:** run the PIT SQL on prod and the `fetch_open_market_buys` live probe. **If confirmed there too, the insider family's forward evidence is void and must be restarted from a fixed clock — the survivor list goes from four to three.**
2. **Today:** patch `quantile_return_spread` (5 lines). Re-read every factor result the bench has produced on a sparse signal.
3. **This week:** publication-lag shift on FRED, then re-run walk-forward. **Expect the AUC/Brier headline numbers to move materially — that re-measurement is the real result.**
4. **This week:** make `pit_score_collector` refuse to write on failure; make `degraded` mean "the live leg worked."

---
# PART V-C — THE EXTERNAL GOLD STANDARD, AND WHAT N=179 ACTUALLY COSTS

*All formulas below are reproduced from primary sources. The Bailey–López de Prado worked example was reproduced to 4 decimal places, which confirms the transcription is exact.*

## V-C.1 The False Strategy theorem, applied to your 179 candidates

**Bailey & López de Prado (2014), Eq. 1**, proved via Extreme Value Theory:

$$E\left[\max_n \widehat{SR}_n\right] \approx E[\{\widehat{SR}_n\}] + \sqrt{V[\{\widehat{SR}_n\}]}\Big[(1-\gamma)\Phi^{-1}\big(1-\tfrac{1}{N}\big) + \gamma\Phi^{-1}\big(1-\tfrac{1}{Ne}\big)\Big]$$

γ ≈ 0.5772 (Euler–Mascheroni). Under the null of no skill the first term vanishes, leaving a pure multiplier $Z(N)$ on the cross-sectional dispersion of your trial Sharpes.

| N | **Z(N) = E[max SR]/σ_SR** |
|---:|---:|
| 20 | 1.901 |
| 50 | 2.276 |
| 100 | 2.531 |
| **179** | **2.729** |
| 500 | 3.053 |
| 1,000 | 3.255 |

*Monte-Carlo check (200k draws): N=179 exact = **2.7097** vs formula **2.7291** — the approximation is conservative by <1%.*

### The number that should govern the paper

$SE(\widehat{SR}_{ann}) \approx 1/\sqrt{y}$ under the null. So:

| Sample length | σ_SR | **E[max SR] from pure noise at N=179** | 95th pct |
|---|---:|---:|---:|
| 6 years (a confirm window) | 0.408 | **1.11** | 1.41 |
| 10 years | 0.316 | **0.86** | 1.09 |
| **15 years (an explore window)** | **0.258** | **0.71** | **0.89** |
| 21 years (2004–2024) | 0.218 | **0.60** | 0.75 |

> **On a 15-year explore window, 179 pure-noise strategies produce a best-of-set annualised Sharpe of ≈0.71 in expectation and ≈0.89 at the 95th percentile.**
>
> **A survivor with a backtest Sharpe of 0.7 carries literally zero evidence of skill — that is exactly what 179 coin flips deliver.**

In t-units this is **t ≈ 2.73** (expected) and **t ≈ 3.44** (95th pct). Note the convergence with the independently-derived Harvey-Liu-Zhu Bonferroni hurdle at N=179 (**t = 3.63**) and BHY-rank-1 (**t = 4.06**). Two entirely different derivations land on **t ∈ [2.7, 4.1]**.

> **A t of 2.0 on a survivor of 179 trials is not weak evidence. It is evidence *against* the strategy — noise alone should have delivered more.**

### ⚠️ The correction that makes this worse, not better

Bailey–LdP define $V[\{\widehat{SR}_n\}]$ as the **empirical cross-sectional variance of your actual trial Sharpes**, not the theoretical null. In their own worked example the implied σ_SR was **1.58× the null value**. Your 179 candidates span heterogeneous families (event-driven, momentum, insider, options, LLM), so their dispersion will exceed the homogeneous null:

| σ_SR (empirical, annualised) | SR₀ hurdle at N=179 |
|---:|---:|
| 0.258 (null, 15y) | 0.71 |
| 0.40 | 1.09 |
| 0.50 | 1.37 |
| 0.707 (their example) | 1.93 |

> **ACTION: compute the actual standard deviation of the 179 Sharpes you measured, and use it. If the ledger recorded them, that is the single most valuable statistic in your entire archive — and it is a one-line calculation.**

### "I don't know my true N" is not a defence

$Z(N)$ grows like $\sqrt{2\ln N}$, so errors are heavily damped:

| N | Z(N) | vs N=179 |
|---:|---:|---:|
| 45 (if candidates are correlated) | 2.236 | **−18%** |
| **179** | **2.729** | — |
| 358 (2×) | 2.951 | **+8%** |
| 716 (4×) | 3.159 | +16% |

**Doubling N raises the bar only 8%.** And the argument runs against you: **179 is a floor**, because it counts registered candidates, not the parameter variations, lookback windows, and universe choices tried *within* each.

## V-C.2 Deflated Sharpe at N=179

$$\widehat{DSR} = \Phi\left[\frac{(\widehat{SR} - \widehat{SR_0})\sqrt{T-1}}{\sqrt{1 - \hat{\gamma}_3\widehat{SR} + \frac{\hat{\gamma}_4-1}{4}\widehat{SR}^2}}\right]$$

**DSR over a 15-year sample at N=179, σ_SR at the *generous* null value:**

| Backtest SR (ann.) | DSR, normal | DSR, skew −1 / kurt 8 |
|---:|---:|---:|
| 0.8 | 0.642 | 0.626 |
| 1.0 | 0.868 | 0.830 |
| **1.2** | **0.968** ✓ | 0.937 |
| **1.5** | 0.998 ✓ | **0.990** ✓ |

> **You need a backtest Sharpe of ~1.2 (normal returns) or ~1.5 (fat-tailed) over 15 years to clear DSR = 0.95 at N=179 — under the most generous σ_SR assumption available.**

**Reproduction check:** BLdP's own example — a strategy with annualised **Sharpe 2.5**, 5 years of daily data, skew −3, kurtosis 10, N=100 — yields **DSR = 0.9004, i.e. REJECTED.** What killed it was not the Sharpe (excellent) but the combination of N=100 and the higher moments. Fat tails matter as much as trial count.

## V-C.3 The principled way to justify a hurdle below 3.0

This is the rigorous answer to "can we lower the confidence level" (cf. Part IX.1).

**Harvey (2017 AFA Presidential Address)** gives the minimum Bayes factor, $\text{MBF} = \exp(-Z^2/2)$, and the symmetric-descending variant $\text{SD-MBF} = -e\cdot p\cdot\ln(p)$.

**Probability the null is TRUE, given a "significant" result:**

| z | p | Prior 4:1 against | Prior 1:1 |
|---:|---:|---:|---:|
| **1.960** | **0.05** | **0.37** | 0.13 |
| *SD-MBF:* 1.960 | 0.05 | **0.62** | **0.29** |
| 3.291 | 0.001 | 0.02 | 0.004 |

**A p=0.05 result on a hypothesis you thought 20% likely a priori leaves a 37% chance the null is true — or 62% under the more conservative SD-MBF.**

**t-thresholds needed to hold P(null) at 5%:**

| Prior | MBF | SD-MBF |
|---|---:|---:|
| 19:1 against (a long shot) | 3.43 | **3.86** |
| 4:1 against | 2.94 | **3.41** |
| **Even odds (well-motivated)** | **2.43** | **2.93** |

> **The hurdle depends on economic plausibility, and this is the only defensible route to a bar below 3.0: a well-motivated hypothesis at even odds needs t ≈ 2.4–2.9; a long shot needs t ≈ 3.4–3.9.**
>
> **But the prior must be fixed BEFORE seeing the result. Setting it afterward is p-hacking with extra steps.**

## V-C.4 Harvey's ticker-letter demonstration

Harvey had an RA form long-short portfolios on the **first, second and third letters of the ticker symbol** — 3,160 letter portfolios × 2 sample periods × equal/value weighting × 2 rebalance frequencies = **25,280 choices** — and return the max-t result.

**Result: t = 3.23**, clearing HLZ's 3.00 hurdle, with near-zero market beta and an average return exceeding the market.

**The factor has no content whatsoever.** This is the single best argument for why survivor-selection accounting is mandatory, and it belongs in your paper.

## V-C.5 What a 55-day lane can and cannot resolve

| Live window | SE(annualised Sharpe) | Sharpe needed for t=2 |
|---|---:|---:|
| **55 trading days** | **±2.14** | **4.28** |
| 252 days (1y) | 1.00 | 2.00 |
| 504 days (2y) | 0.71 | 1.41 |
| 756 days (3y) | 0.58 | 1.15 |

> **A 55-day lane has a standard error on its annualised Sharpe of ±2.14. It cannot distinguish a Sharpe of 0 from a Sharpe of 2.**
>
> **Your 24-month no-skill-claims rule is not conservatism. It is the arithmetic minimum — and even at 24 months the SE is still ±0.71.**

**What a short live period CAN do, with high power — and what the lanes should therefore be used for:** falsify *implementation*. Did the trades fire? Did fills match assumptions? Did turnover match the backtest? Did the cost model hold? Those questions are answerable at 55 days. **Performance is not.**

*(This is exactly what Part V-B found: the lanes were silently not firing — L1's dead insider collector and L8a's frozen smartgrowth clock are precisely the class of defect a short live window is powerful against, and the current surfaces missed both.)*

**Years of live data needed at 80% power:**

| True annual Sharpe | to t=2 | to t=3 |
|---:|---:|---:|
| 0.3 | 87y | **164y** |
| **0.44 (HLZ's estimate for a genuinely TRUE factor)** | ~40y | ~76y |
| 0.5 | 31y | **59y** |
| 1.0 | 7.8y | 14.8y |

**HLZ estimate the average annual Sharpe of a genuinely true factor at 0.44.** Read that row.

## V-C.6 The CPCV objection that governs practice

The published critique literature on CPCV is thin — I found no peer-reviewed head-to-head vs walk-forward. But there is a **structural** objection that is not seriously contested:

> **CPCV trains on data that post-dates the test fold.** For folds where the test group is early in the sample, the model is fit on the future. That is legitimate for estimating *generalization error* — "does this relationship exist in this data-generating process?" — but it is **not a simulation of a deployable strategy.** You could never have run it.
>
> **CPCV's Sharpe distribution answers a scientific question; walk-forward answers the allocation question. They are not substitutes, and only walk-forward is admissible as evidence for putting money on.**

Two further live objections:
1. **Path correlation.** CPCV(6,2)'s 5 paths come from 15 overlapping splits over one sample. Effective sample size is far below φ. **Never treat φ paths as φ independent backtests.**
2. **Cross-sectional leakage — the gap purging does not close.** Purging and embargo operate on the **time axis only**. In a panel, AAPL-on-date-t and MSFT-on-date-t share market-wide shocks. **A time-purged split can still put one in train and the other in test. You must additionally group by date.** For a cross-sectional signal, date-grouping matters more than embargo length.

**Defensible purge/embargo for daily data with 21-day labels:**

| Parameter | Value |
|---|---|
| **Purge** | **≥ 21 trading days** each side — must cover the full label span. Not a tuning knob |
| **Embargo** | **max(1% of T, 2× feature lookback)**. On 20y daily, 1% = **50 days** |
| **Also required** | **group by date** across the cross-section |

**The definitive control** — and you already have the right instinct here — is running the whole pipeline on **shuffled labels**. Your AUC-0.78-from-noise demo is exactly the correct exhibit. If it produces signal, no amount of embargo tuning fixes a structural leak.

## V-C.7 Pre-registration: how rare, and what it buys

**Kaplan & Irvin (PLOS ONE 2015)** — 55 large NHLBI cardiovascular trials, 1970–2012. Registration became effectively mandatory in 2000:

| Period | Trials | Showed significant benefit |
|---|---:|---:|
| **Pre-2000** (0% registered) | 30 | **17 (57%)** |
| **2000+** (100% registered) | 25 | **2 (8%)** |

**χ² = 12.2, p = 0.0005.** And the smoking gun: among the 25 pre-registered trials, **12 reported significant effects on *secondary* outcomes** — nearly half could have reported a positive result had they not declared a primary outcome in advance.

> **Pre-registration cut the apparent success rate by a factor of 7. Not because the treatments got worse — because declaring the primary outcome in advance removed the ability to select it afterward.**

**In finance, pre-registration of observational research is essentially nonexistent.** The AEA registry (12,514 studies) covers RCTs only. Registered Reports exist at ~5 finance/accounting journals out of 300+ overall. **I could locate no public analogue among individual quants.**

> **Your ledger of 179 is not an embarrassment. It is the precondition for honest inference. The typical practitioner has run 179 trials too — they just don't know it, and therefore cannot compute any of §V-C.1.**

**The one self-audit required:** count the parameter variations, universe choices, and lookback windows tried *within* each registered trial. If a "single" trial involved 8 lookbacks, N is not 179.

## V-C.8 The allocation gate

Allocate real money only when **all** hold simultaneously — these are conjunctive, not alternatives:

1. **Pre-registered** before data accrued, with the code hash frozen.
2. **DSR ≥ 0.95** at honest N with **empirical** σ_SR and actual skew/kurtosis.
3. **PBO < 0.10** via CSCV over the full candidate set. *(PBO measures the search, not the survivor — it is the correct diagnostic for a 179-candidate programme, and it is cheap: you only need the N trial P&L series.)*
4. **t ≥ 3.0** (**≥3.6 at N=179**), and the sign matches an ex-ante economic mechanism.
5. **Net of conservative costs**, with **break-even cost ≥ 2× your realistic estimate**.
6. **Survives NYSE-breakpoint value-weighting** — not a microcap artifact. *(Hou-Xue-Zhang: **65% of 452 anomalies fail t>1.96** under NYSE-VW, rising to **82%** at t>2.78; **96% of trading-frictions anomalies fail**.)*
7. **≥ 24 months live paper**, evaluated against the pre-registered rule, not re-litigated.
8. **Size to the haircut Sharpe, not the backtest Sharpe.**

**And the capacity warning nobody quotes** — Hou-Xue-Zhang's own table: NYSE value-weighted implementations carry **$1.3–2.8 trillion** capacity; equal-weighted implementations carry **$1–52 billion**. **Equal-weighting buys statistical significance by borrowing from capacity by 2–3 orders of magnitude.** Aegis's lanes are equal-weighted or HRP — fine at $100k, but the paper must state which regime it is measuring.

---
# PART VI — EXTERNAL RESEARCH

## VI.1 Regime switching and strategy mixing — the core thesis, tested

**Murat's thesis:** *"beat the S&P 500 by mixing strategies and switching between them based on the market phase."*

That sentence contains two claims with **opposite evidence**.

### VI.1a Mixing: well-supported

Diversification across genuinely different return sources, held constantly and rebalanced with bands, is the closest thing to a free lunch in this literature.

- **Baltussen, Martens & van der Linden (2026, FAJ 82(1)), 222 years of data:** *Defensive Absolute Return* and *trend-following* provide "the most consistent and cost-effective downside protection." Gold and put options are **less** drawdown- and cost-effective. This is the broadest defensive-strategy horse race available.
- **AQR's realised record** is the strongest recent live evidence: Absolute Return **+44%** and Alternative Trend **+48.9%** in 2022, when SPY was ~−18%. ⚠️ But it is one regime, and the same funds structurally lag in equity bull markets (Diversifying Strategies +13.3% in 2024 and +16.4% in 2025 — respectable, did not beat the S&P).
- **Rebalancing mechanics:** roughly **half** the excess growth from volatility harvesting comes from diversification and half from the rebalancing mechanic. **Trigger-based (band) rebalancing beats calendar rebalancing** with lower transaction costs.
- ⚠️ **Critical structural caveat:** the rebalancing benefit **collapses as correlations rise** — and correlations rise in exactly the bear regimes you are defending against (Ang & Bekaert). A constant blend's rebalancing bonus is weakest when you most need it. This is the honest argument *for* adding a risk-scaling overlay.

### VI.1b Switching on market phase: poorly supported for return

**The cleanest out-of-sample test available** — Shu, Yu & Mulvey (2024, *Journal of Asset Management*), S&P 500 / DAX / Nikkei, 1990–2023, **net of 10bps one-way and a 1-day execution delay**:

| S&P 500, 1990–2023 | Buy & Hold | HMM-guided | Jump Model |
|---|---|---|---|
| Sharpe | 0.48 | 0.54 | **0.68** |
| Max drawdown | −55.2% | −28.9% | **−26.6%** |
| **CAGR** | **10.2%** | **8.5%** | 11.2% |
| Volatility | 18.2% | 11.3% | 13.1% |
| **Annual turnover** | 0% | **141%** | **44%** |

**Read the HMM column carefully: the regime-switcher earned 1.7 percentage points per year LESS than buy-and-hold.** Its Sharpe improvement came entirely from de-risking. The jump model beat B&H on return only because it cut turnover ~3×. That 141% vs 44% gap, for the same economic idea, *is* the regime-switching problem in one number.

Nystrup et al. state the constraint directly: *"if the inferred regime changes too often, this results in excessive trading costs and inferior performance."*

**The professional base rate is worse still:** Morningstar found **70% of tactical asset-allocation funds underperformed a simple balanced index fund**; over 15 years the average TAA fund returned 3.4%/yr vs Vanguard Balanced's 6.6% — **lagging by 3.2pp/yr at similar risk.** These are funded, staffed, full-time regime switchers.

### VI.1c The ex-post identification problem

This is the most important methodological item in the whole review.

An HMM produces two different state estimates. **Smoothed** probabilities use the whole sample (including the future) — they are what makes regime charts look convincing. **Filtered** probabilities use only data up to *t* — they are the only tradable thing. A published demonstration runs the identical allocation rule both ways: **Sharpe 0.78 filtered, 1.74 smoothed.** Same strategy, same data; the entire difference is lookahead. ⚠️ (Source is a public replication repo, not peer-reviewed — treat the magnitude as illustrative, the direction as certain.)

**Operational rule:** any regime probability used for a decision at time *t* must come from a model whose parameters were estimated only on data ≤ *t*, **and from a filter, not a smoother.** Re-estimating the HMM on the full sample and then "walking forward" the states is still leakage — the transition matrix and state means encode the future.

### VI.1d The sample-size arithmetic **[DERIVED]**

- NBER dates **7 completed recessions since 1970**. ~15 equity bear markets since 1950.
- 56 years of monthly data = 672 observations but only **~14–16 independent regime transitions.** Daily sampling multiplies observations without adding a single episode.
- A 4-regime, 4-asset Guidolin-Timmermann-style model needs 4×(4 means + 10 covariance entries) = 56 state parameters + 12 transition probabilities ≈ **68 parameters against ~15 independent events** — 4.5 parameters per episode.
- **The bear-state mean is the worst-estimated quantity.** Cumulative bear time since 1950 ≈ 8–10 years; at 30% bear vol, SE of the bear-state mean ≈ 30%/√9 ≈ **±10 percentage points per year.** You are conditioning allocations on a number you cannot pin down to within 10%/yr.
- **The detection floor:** SE(SR) ≈ √((1+SR²/2)/T). To establish a **0.10 annual Sharpe improvement** at 5% significance requires **T ≈ 384 years.** Even a 0.25 improvement needs ~61 years.

**Implication: a solo researcher cannot statistically validate a regime-switching *return* claim on 50 years of data.** You *can* validate a risk-reduction claim (drawdowns and volatility are estimated far more precisely than means) and a turnover/cost claim exactly. **Design hypotheses around what is measurable.**

### VI.1e What works instead

**Volatility targeting** is the most reliable item in the entire external review, and it is still small:
- **Moreira & Muir (2017, JF)** — large alphas from scaling exposure by 1/σ̂².
- **Cederburg, O'Doherty, Wang & Yan (2020, JFE)**, the definitive critique, across **103 strategies**: the spanning-regression alphas replicate, but the implied strategies are **not implementable in real time**, and reasonable OOS versions **do not beat the unmanaged portfolios**. Root cause: structural instability in the spanning regressions.
- **Harvey et al. (2018, JPM), 60 assets from 1926** — the reconciliation and the number to plan around: **US equities Sharpe 0.40 → 0.48–0.51. That is +0.08 to +0.11, not +0.5.** Works for risk assets only (leverage effect); negligible for bonds/FX/commodities. **The bigger benefit is left-tail truncation across all asset classes.**

**Trend overlay** has the longest evidence base: 222 years, ~30% drawdown reduction in 2008 and 2020 from a 10% sleeve, and it requires **no regime label** — only a moving average or a 12-month return sign. ⚠️ Counter-evidence held simultaneously: over the 3 years to Aug 2025 the typical systematic trend fund **lost 2.3%/yr** while a balanced index made +12.6%/yr. **Trend is a decade-scale insurance premium, not a return enhancer.**

**Factor momentum** is the one factor-timing signal with a positive cost-adjusted verdict (Robeco/Blitz): it adds active return pre-cost, of which **"almost half can be salvaged after transaction costs."** Valuation-spread timing does not qualify (Asness et al.; Dichtl et al.).

**Asness's decomposition test** — apply this to any switching design: split it into (static tilt + timing residual) and check whether the residual earns anything. *Timing is often a disguised, worse-executed static tilt.*

### VI.1f Implementable designs, ranked

**Tier 1 — do these:**
1. **Static diversified blend, band rebalancing (±5% or 20% relative), tranched over 4 weekly sub-portfolios.** Deterministic; removes up to ~220bps of CAGR "rebalance timing luck" noise.
2. **Volatility targeting on the equity sleeve** (target 10–12%, realized-vol estimate, **cap leverage at 1.0× — de-risk only**). Expect **+0.08 to +0.11 Sharpe** plus meaningful tail truncation.
3. **Trend overlay sleeve (10–20%)** — 12-month TSMOM or 10-month SMA. Test *specification robustness across lookbacks*; fragility is the real risk.

**Tier 2 — pre-register and expect a null:**
4. **Turbulence/absorption-ratio risk *dial*** — continuous de-risking as a function of the standardised AR shift, **never a binary on/off**. Kritzman's own caveat: the absorption ratio is "near necessary but not sufficient" for a decline — high recall, low precision.
5. **Factor-momentum-based sleeve weighting** (Dynamic-1/N style, low turnover).
6. **Statistical jump model** (regime signal with an explicit switching penalty) setting equity exposure only. ⚠️ Single-paper evidence; the jump penalty is a tuned hyperparameter — tune by time-series CV only and haircut by √(2 ln N).

**Tier 3 — do NOT build as a solo researcher:**
7. Multi-regime HMM driving strategy selection (68 parameters vs 15 episodes; the one clean OOS test shows it losing to B&H).
8. Macro-nowcast quadrant classifier (7 recessions = 7 data points; Goyal-Welch: half of published predictors fail OOS; Blitz: business-cycle indicators don't explain factor cyclicality).
9. Valuation-spread factor timing (doesn't survive costs; mostly duplicates a static value tilt).
10. Discretionary/LLM regime calls (no pre-registration possible, unbounded researcher degrees of freedom).

### VI.1g The reformulation the evidence actually supports

> **A constant blend of weakly-correlated return sources, with continuous risk scaling (vol target + turbulence dial) and a trend overlay, rebalanced on bands with tranched execution.**

Expect it to **lose to SPY in strong bull markets**, beat it substantially in 2022-type regimes, and deliver a modestly higher Sharpe with materially smaller drawdowns over a full cycle. **That is a real, defensible, publishable result. "Beats SPY on CAGR after costs" is not, on current evidence, a claim this project will be able to establish — and the honest version of the paper is stronger for saying so.**

### VI.1h The prior you should hold

**SPIVA, year-end 2025:**

| Horizon | % of US large-cap active funds underperforming the S&P 500 |
|---|---|
| 1 yr (2025) | **79%** (4th-worst in 25 years) |
| 10 yr | **91.5%** |
| 15 yr | **98.1%** |
| 20 yr | **95.5%** |

After 15 years **no equity or fixed-income category** had majority active outperformance. **~64% of domestic stock funds were closed or merged away over 20 years**, so the reported numbers *understate* the difficulty. Persistence is worse: **not a single top-quartile domestic equity fund from Dec 2020 remained top-quartile over the next four years**; only **4.2%** stayed in the top *half* over five years.

**P(a given systematic strategy beats SPY over 10y after costs) ≈ 5–10% for professionals.** There is no reason a solo researcher's prior should be higher.

---

## VI.2 Portfolio construction: how the money should actually be allocated

This section answers Murat's direct questions: *how many stocks, equal shares or weighted, what about $1M?*

### VI.2a How many positions

**The mechanical answer.** For an equal-weighted book: σ_p = σ̄ · √(ρ + (1−ρ)/N). The systematic floor is σ̄√ρ — no N gets you below it.

US large/mid calibration (σ̄ = 35%, ρ = 0.25 → floor 17.5%):

| N | σ_p | excess vol over floor | diversifiable variance left |
|---|---|---|---|
| 10 | 19.95% | +2.45 pp | 10% |
| 20 | 18.77% | +1.27 pp | 5% |
| **30** | **18.35%** | **+0.85 pp** | 3.3% |
| **50** | **18.02%** | **+0.52 pp** | 2.0% |
| 100 | 17.76% | +0.26 pp | 1.0% |

**Small/mid caps need ~1.7× the N of large caps for the same residual drag.** This is the most under-appreciated number in the debate — and it applies directly to the `smallmid-quality` lane, which holds **30 names**.

**The literature has drifted upward for a reason:** Evans & Archer (1968) said 8–10 — but they declared victory at a **+4.1pp residual gap**. Statman (1987) said 30–40; Statman (2004) revised to **300+**. Domian, Louton & Racine (2007), "100 Stocks Are Not Enough," made the key methodological shift: measure **terminal-wealth shortfall over 20 years**, not one-period SD. *Volatility converges fast; terminal-wealth dispersion does not.*

**Bessembinder's skewness makes concentration structurally hostile.** **1,092 of ~25,900 CRSP firms (4.3%)** account for the entire $34.8tn of net wealth creation above T-bills, 1926–2016. **~90 firms (0.36%) account for more than half.** The **majority of individual stocks have lifetime returns below one-month T-bills.**

Monte Carlo, 10-year buy-and-hold **[DERIVED]**:

| N | median terminal wealth | mean | P(lose money over 10y) |
|---|---|---|---|
| 1 | 0.94× | 2.57× | **51.8%** |
| 10 | 1.75× | 2.59× | 25.6% |
| 30 | 1.91× | 2.59× | 20.3% |
| 50 | 1.95× | 2.59× | 18.8% |
| 100 | 1.99× | 2.60× | 17.5% |

**The mean is flat in N (2.57–2.60× everywhere).** Diversification does not raise expected wealth — it **drags the median toward the mean** (0.94× → 1.99×, a +112% improvement in the typical outcome). This is a pure skewness argument, not a variance argument, and it is the strongest case against concentration.

**The concentration counter-case, honestly:** Antón, Cohen & Polk find a manager's highest-conviction position outperforms by **2.8–4.5%/yr**; Petajisto finds the highest-Active-Share stock pickers beat by **+1.26%/yr net**. **But** — the decisive critique — ACP measured best-idea alpha **inside diversified 100+ stock portfolios**. It says a top-ranked *signal* has alpha; it does **not** say a 10-stock book is optimal. The empirical carnage: Janus Twenty −69% (2000–02), ARK Innovation −48% since Dec 2021 with an estimated **$14.3bn of destroyed shareholder value**.

**The real tradeoff.** Hold IC at 0.03, TC 0.6, residual vol 25%:

| N | tracking error | IR | E[alpha] | 1-sd-bad-year (α − TE) |
|---|---|---|---|---|
| 10 | 7.91% | 0.20 | 1.56% | **−6.35%** |
| 30 | 4.56% | 0.34 | 1.56% | −3.01% |
| **50** | **3.54%** | **0.44** | 1.56% | −1.98% |
| 100 | 2.50% | 0.62 | 1.56% | −0.94% |

**Expected alpha is identical across the whole table.** Concentration does not raise expected outperformance for a given IC — it raises the *variance* of outperformance. Strictly worse unless your IC is genuinely higher on your top names.

**Verdict: 40–70 names for a $1M active book. 50 is the efficiency knee.** Any small-cap sleeve needs **≥40 names on its own**. Concentrate *within* the book (weights spanning 1.0%–3.5%), not by shrinking it.

### VI.2b Equal weight or return-weighted?

| Scheme | Inputs | OOS evidence | Verdict |
|---|---|---|---|
| **Equal weight (1/N)** | none | **Beats or matches 14 optimizers** (DeMiguel-Garlappi-Uppal 2009) | **Default. Hardest to beat** |
| Cap weight | prices | Is the benchmark | As of 2026 it's a 41.5% bet on 10 names |
| **Inverse vol (1/σ)** | N variances | Robust; captures most of risk parity's benefit | **Best cheap upgrade over 1/N** — only N parameters, all well-estimated |
| Risk parity (ERC) | full Σ | Between 1/N and min-var | Good; far less Σ-sensitive than MV |
| Minimum variance | full Σ | Best realized Sharpe among risk-based — **only with shrinkage** | Expect huge negative active beta, **effective N ≈ 15** |
| **HRP** | Σ, no inversion | **Lower OOS variance than min-var itself** (López de Prado 2016) | **Best Σ-aware choice at N ≥ 40.** Works on singular Σ |
| **Mean-variance (sample)** | μ and Σ | Loses to 1/N | **Do not use** |
| Black-Litterman | Σ, prior, views | Right *architecture* (shrinks views toward equilibrium) | Usable — but overconfident views reproduce MV's pathology exactly |
| Signal-proportional (w ∝ α) | expected returns | This is MV with Σ = I | Only via the Grinold framework, **with caps** |

**Why the optimizers lose.** DeMiguel-Garlappi-Uppal's killer number: the estimation window needed for sample MV to beat 1/N is **~250 years for 25 assets, ~500 years for 50 assets.** For N=50 you must estimate **1,325 parameters**; 10 years of monthly data gives you 600 observations — the covariance matrix is *singular*. And expected returns are worse: SE of a mean over 10 years at σ=35% is **11.1%/yr**. You cannot distinguish a 5% expected return from a 25% one. Optimizers respond by loading maximally on whichever asset was luckiest. This is why MV is called an *error maximizer*.

**Recommendation — two-stage construction:**
1. Signal ranks the universe → take top ~50 subject to sector/liquidity screens.
2. Base weight = **inverse-vol** within sleeve.
3. **Bounded conviction tilt:** w_i = base_i × (1 + k·z_i), k set so weights span ~0.5×–2.0× base.
4. Hard caps: **max 4% single name, max 25% sector**.
5. Swap step 2 for **HRP** once ≥3 years of clean daily data exist on the universe.

Below ~30 names, drop to plain equal weight — any covariance estimate at that N is noise-dominated.

### VI.2c From signal to weight — the arithmetic

**Grinold: α_i = IC × σ_resid,i × z_i**

At **IC = 0.03, σ_resid = 25%**: alpha scale = 0.75%. A **z = +2** name gets **1.50%/yr** of alpha. **That is the entire realistic dispersion of your forecasts.** If your model outputs "this stock will return 40%," it is not calibrated.

Optimal active weight w_i = α_i / (λ·σ²_resid,i). At λ=10: **~2.4% active weight on your best name.** Anyone putting 15% in a single name is implicitly claiming **IC ≈ 0.20** — hedge-fund-with-material-nonpublic-information territory.

**The Fundamental Law, done honestly. IR = TC × IC × √BR.**

The naive calculation (IC 0.03, 100 names, monthly) gives BR = 1,200 → IR = 1.04. **This is wrong, and knowing why is the whole game.**

*Correction 1 — breadth is independent bets, not trades.* With signal autocorrelation g: BR_eff = N·f·(1−g)/(1+g):

| g (signal autocorr) | BR_eff | IR at IC 0.03 |
|---|---|---|
| 0.0 | 1,200 | 1.04 |
| 0.5 | 400 | 0.60 |
| **0.7 (typical value/quality composite)** | **212** | **0.44** |
| 0.9 (slow fundamental signal) | 63 | 0.24 |

*Correction 2 — transfer coefficient.* Long-only with caps: **TC ≈ 0.4–0.6** (unconstrained ≈ 0.95).

**Honest calculation:**
```
BR_eff = 100 × 12 × (1−0.7)/(1+0.7) = 212
IR_raw = 0.03 × √212                = 0.437
IR_net = 0.6 × 0.437                = 0.262
At TE = 4%: gross alpha = 1.05%/yr
```

**Sanity check:** Petajisto's best category — highest Active Share stock pickers — delivered **+1.26%/yr net**. The IC-0.03 arithmetic lands in the same place. **This also calibrates expectations: IC 0.03 is not a modest assumption; it is roughly what the best decile of professional stock pickers achieved.**

### VI.2d Sizing and leverage

**Kelly for US equities** (μ_excess 6%, σ 16%): f* = 0.06/0.0256 = **2.34× leverage**, at 37.5% portfolio volatility. Nobody sane does this.

Growth at fraction c of Kelly = (2c − c²)·g*:

| c | leverage | % of max growth | portfolio vol |
|---|---|---|---|
| **0.50** | **1.17×** | **75.0%** | 18.8% |
| 1.00 | 2.34× | 100% | 37.5% |
| **2.00** | **4.69×** | **0%** | 75.0% |

**The curve is flat on the left and catastrophic on the right.** Half-Kelly keeps 75% of growth at half the vol. Double-Kelly has **zero** long-run growth.

**The estimation-error penalty [DERIVED]:** even with **50 years** of data, the 1-sd band on your Kelly estimate spans **1.46× to 3.23×**. Since overbetting loss is quadratic and underbetting loss is nearly flat, the asymmetry alone forces you well below the point estimate. **Half-Kelly is the defensible upper bound; quarter-Kelly if μ comes from a backtest.** For a long-only equity book: **1.0× notional, no leverage** — you are already at roughly half-Kelly simply by being fully invested.

### VI.2e Costs at $100k vs $1M — the square-root law

**I = Y · σ_daily · √(Q/ADV)**, Y ≈ 0.4–1.0.

**The requested case: $1M book, 2% position ($20k), small-cap with $5M ADV, σ_daily 2.5%:**
```
Q/ADV     = 20,000 / 5,000,000 = 0.4%
I (Y=1.0) = 0.025 × √0.004 = 15.8 bps one-way
Round trip: ~16–32 bps impact + ~45 bps spread ≈ 60–75 bps all-in
At 120%/yr turnover: 0.72–0.90%/yr of drag — most of a realistic alpha
```

Same trade across AUM:

| Book | 2% clip | Q/ADV | one-way impact |
|---|---|---|---|
| $100k | $2,000 | 0.04% | **5.0 bps** |
| **$1M** | **$20,000** | **0.40%** | **15.8 bps** |
| $10M | $200,000 | 4.0% | **50.0 bps** |
| $100M | $2,000,000 | 40% | **158 bps** — you *are* two days of volume |

**Impact budget scales with √AUM, so AUM capacity scales with impact².** Tolerating 4× the impact buys 16× the AUM.

Full annual drag by sleeve at $1M: large cap **0.03%**, mid cap **0.14%**, small cap **0.78%**, micro cap **2.01%**. At $10M small cap becomes 1.30%; at $100M, 2.94%.

**Conclusion: at $100k–$1M you have a genuine, structural capacity advantage in small caps that no institution can access.** That is the single best argument for the `smallmid-quality` lane's existence — and it should be stated in the paper.

**Broker execution matters more than most signal work:** Schwarz et al. (2025, JF) placed identical orders across brokers and found **round-trip costs from 7 bps to 46 bps** — a 39 bp spread on identical orders.

**Which signals survive costs at all:** Novy-Marx & Velikov — anomalies under **~50%/month turnover** generate significant net spreads; few above that do. **Their best mitigation is a buy/hold spread** — stricter thresholds to enter than to maintain (e.g. buy at rank ≤ 40, sell only at rank > 80). That single change typically halves turnover at minimal alpha cost. **It is the highest-ROI implementation detail in this entire document, and Aegis does not currently do it.**

### VI.2f Tax drag — the number that dominates everything

**tax drag ≈ turnover × gross return × tax rate**

20-year after-tax simulation ($1 initial, 10%/yr gross) **[DERIVED]**:

| Strategy | terminal wealth | after-tax CAGR | vs index |
|---|---|---|---|
| Index buy-and-hold (3% turnover, LT) | **$6.18** | 9.53% | — |
| Active, 30% turnover, LT | $5.36 | 8.75% | **−0.78 pp** |
| Active, 60% turnover, LT | $5.18 | 8.57% | **−0.96 pp** |
| **Active, 100% turnover, ST @ 32%** | **$4.12** | 7.34% | **−2.19 pp** |
| Active, 100% turnover, ST @ 40.8% | $3.76 | 6.85% | **−2.68 pp** |

**Break-even gross alpha just to match a buy-and-hold index after tax:**

| Strategy | required gross alpha |
|---|---|
| 30% turnover, long-term | **0.86%/yr** |
| 60% turnover, long-term | **1.09%/yr** |
| **100% turnover, short-term @ 32%** | **2.94%/yr** |
| 100% turnover, short-term @ 40.8% | **3.87%/yr** |

**Set this against the Fundamental Law result: an IC-0.03 signal at 100 names produces ~1.0–1.7% gross alpha. A monthly-rebalanced 100%-turnover version in a taxable account needs 2.94% to break even.**

> **The tax drag is roughly 2× the alpha. The strategy has negative expected value before you even consider execution costs.**

**This is the single most important number in this document.**

**Implications, in priority order:**
1. **Run high-turnover sleeves inside a tax-deferred account; run only low-turnover strategies in the taxable account.** Worth **~2.2 pp/yr** — more than any signal you will ever build.
2. If it must be taxable: **cap turnover at 30–40%/yr** and manage the 12-month holding boundary explicitly. Converting ST→LT is worth **17pp of the gain**.
3. **Systematic tax-loss harvesting: 0.5–1.5%/yr with an IC of 1.0.** A larger and far more reliable alpha than any signal in the ledger.
4. **Regime switching is a tax disaster in a taxable account.** Four full switches/yr = 400% turnover, all short-term.

**Regime-switching cost table:**

| full switches/yr | large-cap (40bps RT) | small-cap (90bps RT) |
|---|---|---|
| 1 | 0.40%/yr | 0.90%/yr |
| 4 | 1.60%/yr | 3.60%/yr |
| 12 | 4.80%/yr | 10.80%/yr |

**A regime model flipping the book 4×/yr must produce >1.6% gross (tax-deferred) or >5% gross (taxable, short-term) just to break even.**

### VI.2g Three concrete designs for $1M

**Precondition, non-negotiable: split the $1M by account type before anything else.** Assume $600k taxable / $400k tax-deferred; all high-turnover sleeves go tax-deferred.

**Design A — Core-Satellite (RECOMMENDED)**

| Sleeve | Alloc | N | Weighting | Rebalance | Turnover | Account |
|---|---|---|---|---|---|---|
| SPY/VOO core | **50%** | 1 | — | never | ~0% | Taxable |
| Large/mid quality-value | 20% | 25 | Inverse-vol × conviction | Quarterly + buy/hold spread | 40% | Taxable |
| Small-cap value/quality | 15% | 20 | Equal weight | Semi-annual | 50% | Tax-deferred |
| Cross-sectional momentum | 10% | 30 | Inverse-vol | Monthly | 150% | **Tax-deferred** |
| Cash / vol-target buffer | 5% | — | — | Monthly banded | — | Tax-deferred |

Expected gross alpha ≈ 1.5%; costs 0.25%; tax 0.30% → **net ≈ 0.95%, IR ≈ 0.40 → 87% chance of beating SPY over 5 years, 94% over 10.**
**Regime handling: the only lever is moving the core between 45% and 55%, ≤2× per year. Max cost 0.08%/yr.** If the regime model is wrong, you lose almost nothing.

**Design B — Full Active Multi-Sleeve.** N ≈ 100, TE 4–5%, net ~1.2–1.6%, **IR ≈ 0.30** → 77% chance over 5 years, and a **~28% chance of trailing SPY over any 5-year window**. Choose only if you can articulate why your per-sleeve IC exceeds 0.03.

**Design C — Concentrated Conviction.** N = 20, TE 5.6–8%, **IR ≈ 0.20–0.28**, 1-in-20 bad year ≈ −10 to −14% vs SPY. Only defensible if you genuinely have IC ≈ 0.08–0.10 on your top names.

| | A: Core-Satellite | B: Full Active | C: Concentrated |
|---|---|---|---|
| Tracking error | **2.0–2.5%** | 4–5% | 5.6–8% |
| Expected net alpha | 0.95% | 1.2–1.6% | ~1.0% |
| **Information ratio** | **0.40** | 0.30 | 0.20–0.28 |
| P(beat SPY, 5y) | **87%** | 77% | 68% |
| Worst 1-in-20 relative year | −3% | −6% | −12% |
| Years to prove skill | ~25 | ~43 | ~100 |

**Three things that matter more than any signal in this project:**
1. **Account placement of high-turnover sleeves: ~2.2 pp/yr.**
2. **Broker execution quality: up to 0.39 pp per round trip.**
3. **Systematic tax-loss harvesting: 0.5–1.5 pp/yr, with an IC of 1.0.**

**The sum of those three exceeds the expected alpha of every design above. Build them first.**

---
# PART VI-B — "SMART MONEY" AND ALT-DATA: WHAT SURVIVES

⚠️ **Verification key:** ✅ = fetched and confirmed. ⚠️ = established literature, **not** re-verified this session (the search budget was exhausted) — a lead, not a receipt.

## VI-B.1 The single most important cross-cutting finding in this document

**Three independent lines of evidence are the same fact, and none of them cites the others:**

1. **Drechsler & Drechsler (NBER w20282)** ✅ — the eight major cross-sectional anomalies *"effectively **disappear** within the 80% of stocks that have **low** short fees, but are greatly amplified among those with **high** fees."*
2. **This project's §28 (RANK-DEAD)** — **99.9%** of the `io_level` spread and **88%** of `skew_25d` live in the **short leg a long-only book cannot hold**.
3. **This project's §26** — `io_level` in small caps carried mean rank IC **+4.91%, t 11.29** — one of the largest IC t-stats in the entire 179-candidate programme — against a **gross excess t of +0.02**.

> **Cross-sectional equity signals concentrate in names a long-only retail book structurally cannot hold.**

**This is not a cost problem to be optimised around. It is a constraint that should be applied *before* a candidate is registered, as a universe rule.**

**The actionable form — and it is the cheapest remaining move on the board:** use the **borrow fee as an eligibility filter**. Exclude expensive-to-borrow names from the long book, and stop expecting anomalies to work in the cheap 80%. It is not a signal; it is a universe rule. **It is untested here, and it retrospectively explains two of the project's own largest negative results.**

⚠️ **Gating question to resolve first:** does Interactive Brokers still publish free shortable-shares/borrow-fee files, and with what history? That is the only realistic free fee source. Free fallback: FINRA bi-monthly short interest — staler, worse, zero cost.

## VI-B.2 Family-by-family

**Insider (Form 4)** — the best lag/quality ratio of any family: SOX §403 requires filing within **2 business days**, EDGAR dissemination is immediate, and ownership documents are **structured XML since 2003** (parseable without NLP). Cohen-Malloy-Pomorski ✅: **opportunistic trades +82 bps/mo value-weighted; routine ≈ 0**, and routine is >50% of the universe. Jeng-Metrick-Zeckhauser ✅: purchases **+40–50 bps/mo**, sales ≈ 0, with **~1/6 of the abnormal return arriving within 5 days**.
⚠️ **The decay is the risk:** a 2026 SSRN working paper reports opportunistic alpha falling from ~1.2–1.6%/mo to **~0.3–0.4%/mo**, with **70–80% dissipating between the transaction date and the next trading day** — i.e. before the Form 4 even posts.
**This matches the project's own prior almost exactly** (BRAIN-003: +17 bps/mo net, t 1.40, microcap null, DSR 0.26). **But see Part V-B L1 — the live collector is returning zeros, so this trial is currently measuring nothing.**

**13F — cloning does not work after the lag, and the live evidence is decisive.** ✅ **GURU** (Global X Guru, the flagship high-conviction clone, inception 2012):

| | 1Y | 3Y | 5Y | 10Y | Since inception |
|---|---|---|---|---|---|
| GURU NAV | 30.97% | 23.85% | 7.62% | 12.82% | **12.62%** |
| Its own index | 31.95% | 24.13% | 7.90% | 13.04% | **12.95%** |

**GURU has underperformed its own benchmark at every horizon, including 14 years since inception**, and holds $61M at a 0.75% fee. Global X's activist (ACTX) and international (GURI) clones were liquidated in 2017 ✅; ALFA and IBLN are gone ⚠️.
**The 45-day lag means the oldest position in a filing is up to 135 days stale**, and shorts, derivatives and non-13F assets are invisible.
**This project has now killed eight 13F-derived variants** with the identical signature: real rank information, dead book.

**Congressional — the one genuinely actionable update.** The academic arc reverses twice: Ziobrowski (2004/2011) found outperformance ⚠️; Eggers-Hainmueller ✅ and Belmont et al. (NBER w26975) ✅ found members **underperform** a passive index.
Then **Wei & Zhou, NBER w34524 (Nov 2025)** ✅ — members who later ascend to **leadership** perform like matched peers *before* ascension and beat them by **up to 47 percentage points annually after**. Mechanisms: higher returns when their party controls the chamber; sales precede regulatory actions; buys precede government contracts.
**Critically, they test the outsider question directly:** rebuilding the portfolios on **disclosure dates instead of execution dates** leaves the result *"marginally weaker in statistical significance"* but **still positive and economically meaningful**. They note pointedly that **no ETF tracks congressional *leaders*.**
**The live products argue the opposite for the unconditional version:** NANC beat SPY by **~82 bps in 2025** and is *behind* in 2026 YTD ✅, with the outperformance widely attributed to **large-cap AI/tech concentration, not congressional information**.
> **The actionable change: `TRIAL-CONGRESS-IC` currently scores all members unconditionally — exactly the specification the modern literature says is null. Wei & Zhou say the information is in a conditioning variable the trial does not carry: leadership status.** Leadership rosters are public and point-in-time reconstructable. This is a cheap, purely additive upgrade to an already-live trial.
⚠️ **Existential risk:** a congressional trading ban would be a signal-death event. The 2026 legislative status was not verifiable this session.

**Supply chain / customer momentum — the best untested idea.** ⚠️ Cohen & Frazzini (JF 2008) "Economic Links and Predictable Returns" is **one of the best-replicated anomalies in the literature** (~1.5%/mo long-short). Monthly rebalance, large-cap-compatible, **no short leg required**.
**The data obstacle just dissolved:** Compustat Segments is paid, but **SFAS 131 major-customer disclosures are in 10-K text on EDGAR and are now extractable with an LLM at near-zero marginal cost.** This is the single best justification for the extraction architecture in Part VIII.7.
⚠️ **Caveat:** the project already rejected a *slow monthly basket* version (§12, spread t 0.10). The Cohen-Frazzini construction is different — verify against Chen & Zimmermann's replicated portfolios before registering.

**Options flow** — closed by this project with better receipts than the literature offers (§27: all 7 arms rejected, **DSR 0.0000 in every cell**, O/S *inverted* at t −6.11). Independently, a **2025 JFE paper (Muravyev, Pearson & Pollet)** shows the IV-spread/skew family is a **mechanical artifact of the omitted borrow fee** — OptionMetrics computes IVs with the borrow fee set to zero, and correlation(fee, IV spread) = **−0.62**, rising to −0.75 in the high-fee subsample. After fees, the effect is 22–38% of its original size and insignificant.
> **A legitimate, novel, free use remains:** back out the **option-implied borrow fee** from the ATM IV spread (`h ≈ −(σ_C − σ_P)/√(2π(T−t))`, correlation 0.95 with the Markit fee for Tesla) and use it as a **descriptive short-crowding indicator** — which feeds directly into the VI-B.1 eligibility filter.

**Skip entirely:** satellite/geolocation (Katona et al. show the advantage accrues to *large* institutions — a solo researcher is on the losing side by construction); job postings, web traffic, app downloads (cost >> budget); retail order imbalance (TAQ cost, plus the Barber et al. "A (Sub)penny for Your Thoughts" critique showing the BJZZ signing algorithm mis-signs a large fraction of trades).

## VI-B.3 Ranked shortlist for a solo researcher, 2026

Scores 1–5 (5 best; decay risk scored so 5 = *low* risk).

| # | Family | Evidence | Data cost | Implementability | Capacity | Decay risk | Status here |
|---|---|---|---|---|---|---|---|
| **1** | **Borrow fee as an eligibility *filter*** | 5 | 3 | 5 | 5 | 4 | **Untested. Highest EV. Explains §26 + §28** |
| **2** | Insider Form 4, opportunistic + cluster, large/mid | 4 | 5 | 4 | 4 | 2 | Live — **but currently measuring nothing (L1)** |
| **3** | **Supply-chain / customer momentum via LLM-extracted SFAS 131** | 4 | 4 | 3 | 4 | 3 | **Untested in this construction** |
| **4** | **Congressional, conditioned on *leadership*** | 3 | 5 | 4 | 2 | 1 | Cheap upgrade to a live trial |
| **5** | Short interest as a long-only *exclusion* screen | 4 | 5 | 4 | 4 | 3 | Free; complements #1 |
| **6** | Patent / innovative efficiency (PatentsView) | 3 | 5 | 4 | 4 | 4 | Free, annual, low-turnover. Untested |
| **7** | Aggregate short interest as a *conditioning* variable | 3 | 5 | 3 | 5 | 3 | Not an allocator — timing is closed (§1) |
| **8** | 13F conviction, small/concentrated managers only | 2 | 5 | 3 | 3 | 2 | **Probably a trap** — GURU's 14-year record + 8 dead in-house variants |

**Do not spend a candidate slot on:** options flow / IV skew / O/S / put-call (§27, DSR 0.0000, *and* now explained as a borrow-fee artifact); GEX and 0DTE (volatility mechanics, not return signals; retail options round-trips cost **~13.5% of premium**); 13D/G (§31 — but see Part V, F1: that closure may be a statistical artifact); LLM-alpha-as-trader (§19); FDA/PDUFA (§11, §16); any "abnormal X" residualised construction (three receipts against).

---
# PART VIII — OPTIMUS (THE BRAIN) AND THE LLM LAYER

## VIII.1 Optimus as it exists today

**Location:** `C:\Users\mrthn\optimus\` — a separate git repo (`Murathanx12/Optimus`), wired via `aegis-finance/.mcp.json` (not `.claude.json`), entry point `optimus/mcp/server.py`, talking to prod Railway by default.

**Stack:** plain Python + `FastMCP`. **No embeddings, no vector DB, no LLM in the retrieval path.** Markdown is truth; SQLite is a derived index (6 tables: pages, aliases, edges, claims, tombstones, events).

**Read-only by construction, not convention.** `Store(read_only=True)` opens SQLite in `mode=ro` and every write method raises. A Claude session physically cannot corrupt the brain. This is good design and should not be relaxed.

**Ingestion — three channels:**
- **git channel** — reads `git ls-files` only, so `.gitignore` exclusions are free (no `.env`, no secrets). Emits exactly 3 pages per repo. This is a summary index, not full text.
- **notes channel** (added 2026-08-02) — one fully-indexed page per `.md` file, full body, 256 KB cap, no file-count cap. This is what made trial docs and postmortems actually queryable.
- **folder channel** — older, caps at 40 files, first line only. Now redundant.

**Retrieval scoring** is deterministic keyword/term-overlap with a coverage bonus (+30 × fraction of query terms matched), domain-tier-first ranking, and a **relevance floor of 20.0** calibrated against a probe table. Below the floor it **abstains** (`no_match`) and returns the rejected candidates with scores — a genuinely good design choice that most RAG systems lack.

**Corpus (measured live 2026-08-02):** 169 pages, 236 claims, 438 aliases, across 15 projects in 7 domains (finance, finance-ancestor, robotics, art, school, personal, core).

**Deliberately excluded:** emails and general PC files. Murat asked for "emails, pc files, everything"; this was refused on the grounds that **mixed-domain pollution was the original measured failure mode**, plus privacy. That ruling was correct and should stand.

## VIII.2 Optimus weaknesses

| # | Weakness | Evidence |
|---|---|---|
| 1 | **`brain_query` is the only stale surface.** `aegis_verified_state`, `aegis_canon`, `aegis_postmortems`, `aegis_registry` all read live. `brain_query` answers from whatever was last ingested — with **no staleness field in the answer** | Two projects are stale right now: `aegis-quant-knowledge` (2026-07-10, 3+ weeks) and `aegis-research` (07-29, now redundant) |
| 2 | **`refresh_aegis.py` is manual.** Not scheduled, not a git hook, not run on session start | This exact discipline lapsed once already — the 2026-07-29 audit found the corpus 6 weeks stale |
| 3 | **No usage telemetry on the production surface.** `Store.log_event()` silently no-ops under `read_only`, so the 89 rows in `events` are CLI testing only — **zero real session queries are recorded** | Means retrieval quality on real questions is unmeasurable |
| 4 | **`aegis_canon` is hardcoded to one trial doc** (TRIAL-001). The other ~34 trials are unreachable through it | `server.py:87-91` |
| 5 | **`aegis_registry` has no server-side filtering** — no filter by verdict, metric, or family. A caller wanting "every REJECT in the 13D family" burns context filtering client-side | `server.py:75-84` |
| 6 | **Keyword-only retrieval misses paraphrase.** Asking about "cache poisoning" without the literal source words under-scores even when the concept is present | By design (`core/query.py`) — deterministic, free, snapshot-testable. A real trade-off, not a bug |
| 7 | **`core/distill.py` is fully built and never called.** LLM decision-claim extraction with its own test file, no CLI subcommand, no caller | The notes channel (full-body indexing) is the workaround that made it unnecessary |
| 8 | **`docs/ARCHITECTURE.md` says "Not built: … MCP server … audit"** — both are built and in daily use | An ironic instance of the exact failure the brain exists to prevent |

## VIII.3 Optimus improvements, ranked by leverage ÷ effort

1. **Wire `refresh_aegis.py` into session start or a git hook** *(trivial)* — converts a discipline that has already failed twice into a guarantee. Highest ratio on the list.
2. **Return the ingest commit/timestamp in every `brain_query` answer** *(small — the data already exists in `pages.updated`)* — surface `"as_of": {project: date}` so a session sees "current through `a7077e1`, 3 days old" instead of trusting a match blindly. Closes the staleness gap without touching retrieval.
3. **Retire `aegis-research`** *(trivial)* — stale, capped, first-line-only duplicate of `aegis-research-docs`.
4. **Enable event logging on the read-only path** *(small)* — a separate append-only log file, not the read-only store. Without this you cannot measure whether retrieval works.
5. **"What changed since last session" diff tool** *(medium)* — compare `pages.updated` against a caller cutoff, return new trial verdicts, new NEGATIVE_RESULTS entries, new postmortems. Replaces several tool calls that `/go` currently makes by hand.
6. **Structured filterable registry query** *(medium — needs an Aegis-side API change)* — `?verdict=REJECT&family=13D`.
7. **"Current open decisions" tool** *(medium-large, speculative)* — needs a defined schema for "open" first.
8. **Contradiction detection** *(large, low value)* — the corpus is an append-only research log where later notes deliberately supersede earlier ones; a naive detector would be mostly noise.
9. **Write-back** — **recommend against.** The read-only rail is deliberate architecture, and the sacred `paper_nav` write-path (CANON §5) is exactly what it protects.

---

## VIII.4 The LLM layer: current state

**DeepSeek spend to date: $0.03 of a $19.96 balance.** Live state shows `calls_today: 3` against `daily_cap: 150`.

### Every LLM call site

| Function | File | What it does | Wired to UI? |
|---|---|---|---|
| `summarize_market_news` | `llm_analyzer.py:239` | Prose summary of ≤15 headlines | Yes — news page |
| `argue_signal_two_sided` | `llm_analyzer.py:303` | Bull/bear case from the engine's own signal JSON | Yes |
| `summarize_daily_brief` | `llm_analyzer.py:380` | Structured daily brief | Yes — homepage |
| `analyze_stock_outlook` | `llm_analyzer.py:428` | Headlines + fundamentals → prose | Yes — stock news tab |
| `generate_expectations` | `llm_analyzer.py:504` | Analyst targets → prose | **No — dead code, no caller** |
| `generate_portfolio_commentary` | `llm_analyzer.py:554` | PORT-style commentary | Yes — portfolio page |
| `_classify_llm` (EVENT-INTEL) | `event_intel.py:189` | **Enums only, no prose** — `{event_type, direction, basis}` | Indirectly, via daily brief only |
| `narrate` (explain-move) | `explain_move.py:181` | 3-sentence narration of an evidence dossier | Partially |

All funnel through one chokepoint, `_call_llm` (`llm_analyzer.py:174`). Provider order: Claude if `ANTHROPIC_API_KEY` set, else DeepSeek — so in prod **everything is DeepSeek `deepseek-chat`**, `max_tokens=500`, `temperature=0.3`.

### The guardrails (all good, all worth keeping)

- **Daily cap 150** (`config.py:764`) — process-local counter; when tripped, helpers return `None` and callers fall back to templates.
- **Billing circuit breaker** — a 401/402 or "insufficient balance" trips a 6-hour cooldown.
- **Enums-only by construction** in EVENT-INTEL — invalid enums degrade to `tier="FAILED"` rather than being trusted.
- **Canaries** — per-feed, test a known high-volume ticker; an empty canary marks the feed "suspect" so a dead feed is never reported as "no events."
- **Fail-closed advice filter** — regex on imperative language; `argue_signal_two_sided` discards the *whole* output rather than serving partially-scrubbed advice.
- **"LLM narrates / engine computes"** — codified as CANON §3 + V2_GOALS A2 and **enforced in code**: no LLM output is consumed anywhere as a weight, score, or allocation input.

### ⚠️ FINDING: EVENT-INTEL is dead in production

Live state: `events_extracted: 0`, `feed_calls: {}`, `last_extraction_at: null`.

**Root cause — it has no scheduled entry point and is effectively unreachable:**
1. The scheduler registers exactly 4 jobs (`pi_hourly_mtm`, `pi_daily_check`, `pi_weekly_aggressive`, `pi_congress_collect`). **None calls event-intel.**
2. `GET /api/event-intel/{ticker}` has **zero frontend callers** — the only reference is the type wrapper in `api.ts` and the `/dev` page, which *displays* stats without triggering extraction.
3. The one live path (`_events_block` inside the daily brief) is **gated on the visiting browser's localStorage watchlist**. Empty watchlist → zero tickers → no extraction.
4. Even successful runs write to **in-process counters with no persistence** — a Railway redeploy zeroes them instantly.

The code is correct and tested. It simply never runs. **This is CANON §8's silent-fragility failure mode occurring inside the LLM subsystem** — precisely what the `silent-fragility-audit` skill exists to catch.

### ⚠️ FINDING: the §19 closure is narrower than it is being applied

NEGATIVE_RESULTS §19 closed the **LLM-as-trader** family on three external receipts (withdrawn flagship paper; FINSABER; Glasserman-Lin's "not a feasible strategy"). A scope correction recorded 2026-07-30 — **credited to DeepSeek** — states explicitly that these receipts do **not** close **LLM-as-feature-extractor**, and names EVENT-INTEL as the already-house-legal instance.

**So the largest genuinely untested research direction available to this project is the one it built the infrastructure for and then never switched on.**

---

## VIII.5 What the external literature says about LLM alpha

The published literature splits cleanly, and the split predicts replication almost perfectly:

| Framing | Typical claim | Replication record |
|---|---|---|
| **LLM as predictor** (text → buy/sell, or agent trades) | Sharpe 2–4, triple-digit returns | **Near-zero.** Collapses post-cutoff, collapses under costs |
| **LLM as feature extractor** (text → structured field → conventional model) | Modest incremental R², validated against external ground truth | **Decent.** Survives PIT retraining and audit |
| **Novelty/change measurement** (entropy, similarity gap, 10-K diff) | 1 SD novelty → −3%/yr market; Sharpe 1.03→1.43 as a *filter* | **Best of the three, and cheapest to build** |

### The numbers that matter

**Lopez-Lira & Tang** (the anchor paper): 159,137 firm-headline observations, 4,123 firms, Oct 2021–May 2024. Headline hit rate 93.3% overnight. Drift long-short **34 bp/day**, ~700% cumulative, Sharpe 2.97 — **all pre-cost**. But: **~190% daily turnover**, **unprofitable at 20 bp round-trip**, short leg (SR 2.01) dominates the long leg (0.78), and the Sharpe decays **6.54 (2021Q4) → 3.68 (2022) → 2.33 (2023) → 1.22 (Jan–May 2024)**.

**The single most important row in that paper:** FinBERT classifies direction at 90% accuracy (vs GPT-4's 93%) and produces a **Sharpe of −0.33**. Classification accuracy and tradable signal are nearly orthogonal. Sentiment-accuracy benchmarks are not a proxy for alpha.

**Profit Mirage (arXiv 2510.07920)** — post-cutoff decay across four agent systems: **Sharpe −51% to −62%, returns −50% to −72%**. Memorization audit: 85.4% price recall, 92.9% event-impact recall. Their phrase: *"near-encyclopedic recall rather than predictive capability."*

**The Alpha Illusion (arXiv 2605.16895)** — audits five LLM trading systems: **35 of 40 system × friction cells are unmodeled**. Their own reproduction: gross Sharpe **0.43 → 0.22 net**, both underperforming buy-and-hold.

**Glasserman & Lin (the counter-intuitive one)** — anonymizing company identifiers **improved** long-short returns by 4.4–5.9 bp/day. The **distraction effect** (the model's stored view of the firm interfering with its reading) **exceeds the look-ahead effect**. Design implication: strip entity names.

**Chen, Tang, Zhou & Zhu (arXiv 2502.10008)** — relevant to the budget: **DeepSeek underperforms ChatGPT** on market-risk-premium prediction from WSJ text, as do other open models.

### What survives: the formal statement

**Ludwig, Mullainathan & Rambachan (NBER w33344)** partition LLM uses into two, with different validity requirements:
- **Prediction problems** — require *no training leakage*, enforceable only with open-weight, date-bounded models. Closed frontier models are structurally unauditable.
- **Estimation problems** — require *a small hand-labeled validation sample*. Without one, "seemingly innocuous choices (which model, which prompt) can produce dramatically different parameter estimates."

**The design rule, in one sentence: if there is no verifiable ground truth, the LLM output is not a measurement — it is a vibe with a decimal point.**

### The model to copy: grounded 8-K extraction (arXiv 2607.08346, Jul 2026)

Three-tier taxonomy (8 primary / 29 secondary / **119 tertiary** event types), compact instruction-tuned model, temperature 0, two stages:
- **Stage 1:** schema validation rejecting out-of-taxonomy tags with self-correcting retries, **plus fuzzy n-gram quote validation requiring ≥40% of four-word sequences from the cited quote to appear verbatim in the filing.**
- **Stage 2:** re-read each cited quote against the category definition, score 1–5.
- **Results: 292,984 filings, 601,088 validated tags. Overall precision 72.6%; score-4+ 92.7%; score-5 96.4%.**
- **They make no return-prediction claims.** They measure reaction magnitudes.

**The money finding is the 72.6% → 96.4% precision gradient: a self-grounding score is a calibrated reliability dial you can threshold on.** It converts an unverifiable LLM output into a verifiable one, cheaply.

## VIII.6 What $20 of DeepSeek actually buys

Assume enum extraction: ~1,000-token document + 800-token fixed taxonomy prompt + ~150 tokens output.

| Configuration | Cost/doc | Docs for $20 |
|---|---|---|
| V4-Flash, no caching | ~$0.00018 | **~110,000** |
| **V4-Flash, 800-token prefix cached** | ~$0.00007 | **~275,000** |
| V4-Pro, prefix cached | ~$0.00022 | ~90,000 |
| Long docs (20K-token MD&A), V4-Flash | ~$0.003 | ~6,600 filings |
| Claude Haiku 4.5 via Batch API (50% off) | ~$0.00088 | ~23,000 |

**DeepSeek Flash with prefix caching is ~25× cheaper than batched Haiku.** The prefix cache gives 98% off input, so prompt ordering is worth ~2.5× your throughput: put taxonomy + instructions + few-shot examples **first and byte-frozen**, document last. Any `datetime.now()`, UUID, or unsorted `json.dumps()` in the prefix silently kills the cache.

**Conclusion: the $19.96 balance is not the constraint. The `daily_call_cap: 150` and the dead extraction path are the constraints.** At 275k documents of headroom, this project could process every 8-K filed in a year, several times over, for less than the current balance.

## VIII.7 Recommended LLM architecture

```
Tier 0 — FREE, DETERMINISTIC, NO LLM. Do this first.
  • EDGAR full-text: 10-K/10-Q cosine similarity vs prior filing (Lazy Prices)
  • News novelty: 1 − max cosine sim to that firm's prior-90-day news
  • Entity linkage, dedup, timestamp normalization
  • Attention/volume counts (the Reddit finding: volume beats polarity)
  Cost: $0. Zero cutoff-leakage surface. Highest replication prior in this document.

Tier 1 — LOCAL, FREE: FinBERT / DistilFinBERT
  • Bulk polarity on 100% of the corpus
  • Use it to ROUTE (escalate uncertain docs), never to signal
    (FinBERT scored −0.33 Sharpe in Lopez-Lira)

Tier 2 — DeepSeek V4-Flash (~$15): structured extraction
  • Enum-only against a CLOSED taxonomy, temperature 0
  • Schema validation + retry
  • MANDATORY: verbatim quote citation per field, fuzzy n-gram validated
  • Self-grounding score 1–5; threshold at 4+
  • Long stable prefix → cache hits are the whole ballgame
  Throughput: 150k–275k short docs, or ~5,000 long filings

Tier 3 — Claude (~$5 or subscription): adjudication only
  • YOU hand-label 200–500 documents. Non-negotiable — this is the
    validation sample Ludwig et al. require
  • Claude as second adjudicator on the disagreement set only
  • Never the bulk extractor. Never emitting a position

Tier 4 — CONVENTIONAL: the actual model
  • LLM fields enter as FEATURES into LightGBM/logistic with purged CV
  • Ablation: does the LLM feature add anything over Tier-0 alone?
  • Existing Aegis discipline applies unchanged
```

**Everything in Tier 0 should be built before anything in Tier 2.** It is free, it has no leakage surface, and it has a better replication record than anything an LLM will produce.

---
# PART IX — THE CONTEXT THESIS: WHERE MURAT IS RIGHT, WHERE HE IS WRONG

*This part responds directly to the design questions raised 2026-08-02: lowering the confidence level, abandoning Sharpe for raw ROI, taking more risk, riding trends early and exiting at the peak, and — the central idea — using an LLM plus Optimus to capture the social, political, and narrative context that numbers alone miss.*

**Summary verdict: the central thesis is substantially correct and is backed by a large published literature the project has not yet mined. Three of the four supporting tactics are wrong, and one of them is wrong in a way that would have cost real money.**

---

## IX.1 "Can we lower confidence to 90% or 85%? Even 60%?"

### You are more right than the project's own canon admits — but not for the reason you think

The project uses **Harvey-Liu-Zhu's t > 3.0** hurdle (`METHODOLOGY.md §1.5`). That is one side of a live, unresolved academic fight, and the project has only ever cited one side.

**The other side, with numbers:**

- **Chen & Zimmermann (RAPS 2020)** measured publication-bias shrinkage at **12.3% ± 1.7pp** — not the 50%+ the pessimists assume. Their conclusion: *"the traditional t-stat hurdle of 1.96 can actually be lowered, and even a t-stat hurdle of **1.79** leads to an FDR of **1.0%**."* Against HLZ, who *"find that a t-stat hurdle in excess of **2.88** is required to obtain an FDR of 1%, far above our estimate of 1.79."*
- **Chen, "Do t-Statistic Hurdles Need to Be Raised?" (Management Science, 2025)** — the title is the answer: *"I show these calls may be difficult to justify empirically."*
- **Chen, "Most Claimed Statistical Findings in Cross-Sectional Return Predictability Are Likely True"** (forthcoming, *Journal of Finance: Insights*) — bounds the false discovery rate at **≤ 9%**, and in the simplest form **≤ 25%** across eight of nine prior studies. His own summary: *"At least 91% are true."* The title is a direct rebuttal of HLZ.

**So: yes, a t-hurdle near 1.8–2.0 is defensible, and it is defended in a top-three finance journal.** The project's t > 3.0 is not a neutral standard — it is the strictest position in an active dispute. Adopting a lower hurdle *with the citation attached* is a legitimate, publishable methodological choice.

### But here is why lowering the threshold will not do what you want

**Confidence level and statistical power are different problems, and yours is a power problem.**

From the audit (Part V, F6), computed on the live 37-observation record:

| | at 95% confidence | at 90% | at 85% | at 60% |
|---|---|---|---|---|
| Power to detect a true annualised Sharpe of 1.0 | 5.7% | ~11% | ~16% | ~45% |
| **Minimum detectable Sharpe at 80% power** | **7.31** | ~6.6 | ~6.1 | ~4.4 |

**At 60% confidence you would be "detecting" effects 45% of the time when they are real — and generating false positives 40% of the time.** You have not gained information. You have traded one kind of error for four times as much of another. With 37 observations, no threshold rescues you; **the sample is the constraint.**

### The reframe that actually gives you what you want

**Stop asking "is it significant?" and start asking "what is the posterior expected value, net of costs?"**

This is what professional allocators actually do, and it is a genuinely different framework:

1. **Start from a prior**, not from zero. Chen-Zimmermann's whole point is that the prior for a plausible, literature-motivated predictor is *not* "zero effect" — the dispersion of true effects across predictors is large (σ ≈ 3 in their normalised units; the average standard error is ~20 bps/mo, so *"it's easy to find a predictor with a true expected return of 60 bps per month"*).
2. **Shrink your estimate toward the prior** by the measured 10–15%, not by an arbitrary haircut.
3. **Subtract costs and taxes honestly** (Part VI.2e–f).
4. **Allocate proportional to the posterior mean, sized by the posterior variance** — which is exactly the Grinold formula `w = α/(λσ²)`. A weak-but-positive posterior gets a small weight. It does not get excluded, and it does not get a full weight either.

**Under this framework the question "90% or 95%?" disappears.** There is no threshold. There is a weight that shrinks smoothly to zero as evidence weakens. That is the correct answer to your question, and it is strictly better than either 95% or 60%.

**Concretely for Aegis:** keep t > 3.0 as the bar for *"we claim a discovery in the paper."* Use **posterior-mean sizing** for *"how much capital does this get."* They are different decisions and should never have shared a threshold.

---

## IX.2 "Do we have to depend on Sharpe? Can we make risky moves and maximise ROI?"

### You are right that Sharpe is the wrong objective. You are wrong about what replaces it.

Sharpe is a *portfolio-selection* statistic that assumes you can lever freely. If you cannot lever, or you are compounding a single book over decades, the correct objective is the **geometric growth rate**:

**g = μ − σ²/2**

This is not Sharpe. It penalises volatility *quadratically and directly*, not as a ratio. Run your own question through it:

| Strategy | μ (arithmetic) | σ | Sharpe | **g = μ − σ²/2** |
|---|---|---|---|---|
| SPY | 10% | 16% | 0.50 | **8.7%** |
| "Risky, high return" | 30% | 50% | 0.56 | **17.5%** ✅ |
| "Very risky" | 30% | 80% | 0.34 | **−2.0%** ❌ |
| "Aggressive but diversified" | 20% | 25% | 0.68 | **16.9%** |
| Concentrated 10-stock book | 25% | 45% | 0.49 | **14.9%** |

**Read row 3.** A strategy with a 30% expected return and 80% volatility has a *negative* long-run growth rate. It makes money on average and loses money almost surely. This is the mathematical form of what happened to the mirror lane.

**So: yes, take more risk — up to the point where σ²/2 starts eating μ faster than μ grows.** That point is real, computable, and much closer than intuition suggests. Full Kelly for US equities is 2.34× leverage at 37.5% volatility (Part VI.2d); **double-Kelly has exactly zero long-run growth.** The curve is flat on the left and catastrophic on the right.

### The distinction that actually matters: which risk you take

**Bessembinder is decisive here.** 4.3% of firms generated all net wealth creation since 1926; the *majority* of individual stocks underperformed one-month T-bills over their lifetimes. From the Monte Carlo in Part VI.2a:

| | Median 10y terminal wealth | Mean | P(lose money) |
|---|---|---|---|
| 1 stock | 0.94× | 2.57× | **51.8%** |
| 50 stocks | 1.95× | 2.59× | 18.8% |

**The mean is identical. Concentration does not raise expected wealth — it destroys the median.** Idiosyncratic risk is *uncompensated*: you bear it and get paid nothing for it.

**The correct aggressive posture is therefore precise:**
- ✅ **Take more systematic risk** — higher equity beta, a levered position in a *diversified* thing, longer duration, more small-cap and value exposure. This is compensated.
- ❌ **Do not take more idiosyncratic risk** — concentrated single names, 25% positions, unhedged bets. This is uncompensated, and the mirror lane's −22.4% at beta 1.05 is the receipt: **a −24pp purely idiosyncratic loss.**

**You are young, with decades of horizon and large human capital ahead of you. That genuinely justifies a higher risk target than a retiree — Merton's lifecycle result.** It justifies **1.0–1.3× exposure to a diversified book**. It does not justify 25% in one micro-cap. Those are different decisions that both feel like "being aggressive."

---

## IX.3 "Get in early on a trend and drop at the peak"

**Half right, and the wrong half is the expensive one.**

**The exit half is refuted — by your own data.** NEGATIVE_RESULTS §1: the signal engine's **sell-signal 3-month hit rate was 28.6% against a 55% target**, because sell signals fire at VIX > 25, which is historically the best time to buy. The strategy returned **+250.9% against buy-and-hold's +740.0%.** Peak-detection is the single most thoroughly refuted idea in this repository, and the external literature agrees: crash *timing* has ≈0 IC, and false-positive de-risking costs more than the crashes it avoids.

**The entry half has real support.** Two published mechanisms:
- **Da, Engelberg & Gao, "In Search of Attention" (JF 2011)** — Google search volume predicts higher prices over the next 2 weeks, **followed by reversal within a year.** That is literally "the trend forms, then it unwinds."
- **Barber & Odean, "All That Glitters" (RFS 2008)** — retail investors buy attention-grabbing stocks, creating temporary price pressure.

**The version that survives contact with reality:** enter on momentum **conditioned on rising attention/novelty**, and exit on a **mechanical rule** — a trailing stop or a fixed time stop — **never on a judgment that the peak has arrived.**

**You are already running this experiment and it is currently your best lane.** `conservative-atr` — an ATR Chandelier trailing stop over an otherwise identical mandate — is at **+3.59%**, the top of all 10 lanes. ⚠️ At 55 days that is noise (Part V, F6), but the *design* is the correct expression of your instinct, and it is already pre-registered with a control. **Do not build a peak-detector. Let the stop decide.**

---

## IX.4 The central thesis: social bias, narrative, and context as alpha

**This is your strongest idea, it is backed by a large published literature, and Aegis has barely touched it.**

You wrote: *"there are a lot of profitable companies and they are not increasing and undervalued since they are not mainstream… on the other hand there are a lot of overvalued companies, NVDA, TSLA, and they still increase since they are always on the news."*

**That is a real, named, published anomaly, and it points in exactly the direction you say.**

### The literature that proves you right

| Mechanism | Finding | Why it supports your thesis |
|---|---|---|
| **Fang & Peress, "Media Coverage and the Cross-Section of Stock Returns" (JF 2009)** | Stocks with **no media coverage earn higher returns** than heavily covered stocks, after controlling for size, book-to-market, momentum and liquidity | This is literally "undervalued because not mainstream." Your intuition, published |
| **Hong & Kacperczyk, "The Price of Sin" (JFE 2009)** | Sin stocks (tobacco, alcohol, gaming) are **shunned by norm-constrained institutions**, less covered by analysts, and earn **higher returns** | Social bias creating durable mispricing — your exact mechanism |
| **Hong, Lim & Stein, "Bad News Travels Slowly" (JF 2000)** | Momentum is **stronger in low-analyst-coverage stocks**, and the effect is concentrated in *bad* news | Information diffuses through social networks, not prices |
| **Cohen, Frazzini & Malloy, "The Small World of Investing" (JPE 2008)** and **"Sell-Side School Ties" (JF 2010)** | Fund managers overweight firms whose boards share their **educational network**, and earn significantly higher returns on those positions; analysts are more accurate on school-tie-connected firms | **Network and relationship data predicts returns.** Your "network, founders, connections" point, measured |
| **Cohen & Frazzini, "Economic Links and Predictable Returns" (JF 2008)** | Customer-supplier links predict returns with a lag — investors fail to connect obviously related firms | One of the best-replicated anomalies in the literature |
| **Cooper, Gulen & Ovtchinnikov, "Corporate Political Contributions and Stock Returns" (JF 2010)** | Firms that **contribute more to political candidates** earn higher future returns; the effect scales with the number of supported candidates and with home-state candidates | **"Closeness to the ruling party" is a measured, published return predictor** |
| **Faccio, "Politically Connected Firms" (AER 2006)** | Political connections are common and materially affect firm value, concentrated in countries with high corruption and restricted foreign investment | Your political-influence thesis, cross-country |
| **Acemoglu, Johnson, Kermani, Kwak & Mitton (JFE 2016)** | Firms **connected to Timothy Geithner** saw abnormal stock returns around his nomination announcement | A clean natural experiment on personal political networks |
| **Tetlock, "Giving Content to Investor Sentiment" (JF 2007)** | Media **pessimism predicts downward price pressure followed by reversion**; unusually high or low pessimism predicts high volume | Narrative moves prices, then unwinds |

**Every one of these is a "context and relationships matter more than the numbers" result. You are not being fanciful — you are describing a well-populated research programme.**

### Where the numbers support the context — the synthesis you described

Your framing — *"where numbers support context and logic might not, or vice versa"* — maps onto a concrete, buildable design, and it is the **extraction-not-prediction** architecture from Part VIII.7:

```
CONTEXT LAYER (LLM extracts, never predicts)
  → political connection: lobbying spend, PAC contributions, government
    contract share, regulatory exposure, revolving-door hires
  → network: board interlocks, executive education/employer overlap,
    customer-supplier declarations from 10-K Item 1
  → attention: media coverage count, novelty vs prior coverage,
    analyst coverage count, search interest
  → narrative: event type, direction, novelty (enums only)

NUMBERS LAYER (unchanged, deterministic)
  → the existing quality/value/momentum/insider signals

INTERACTION (this is the actual thesis)
  → "cheap AND neglected" — high gross profitability × zero media coverage
  → "expensive AND crowded" — high valuation × high attention (the short/avoid side)
  → "connected AND cheap" — high lobbying intensity × low valuation
```

**The interaction terms are the idea.** Not "buy neglected stocks" (that's a known factor), not "buy quality" (known factor), but **quality conditioned on neglect** — which is precisely "profitable companies that aren't going up because nobody is looking."

**And this is directly testable with data you may already have.** It is a cross-sectional signal, it needs no LLM to start (media coverage count and analyst coverage count are structured fields), and the LLM only enters to extract the harder context features.

### Where you are wrong, and it matters

**On ethnic background and demographic composition as a signal: do not build this.** Two independent reasons, and neither is squeamishness:

1. **It does not measure what you want.** The economic mechanism you are actually pointing at is *political access and regulatory favour*. Ethnicity is a very noisy proxy for that, while lobbying disclosures, PAC contributions, government contract awards, and revolving-door hires **measure it directly**, are free, and are already validated in the literature above. Using the proxy instead of the measurement is strictly worse research.
2. **A screen that allocates capital by the ethnic composition of a firm's workforce or leadership is a discriminatory screen.** For a project whose entire asset is its published methodological integrity — and which you intend to submit to a journal — that is an unrecoverable reputational and legal exposure for an effect you can capture better by other means.

**Build the political-connection features. They are the real mechanism, they are free, and they are published.** Free sources: Senate LDA lobbying filings, OpenSecrets, USASpending.gov federal contracts, SEC 10-K Item 1A regulatory risk language.

### Where the project has already tested a piece of this and failed

Be aware of what is already closed, so you don't re-run it:
- **§12 supplier/customer momentum** — tested, spread t = 0.10, **REJECTED**. Note this was the *slow monthly basket* version; the Cohen-Frazzini original is a different construction.
- **§17 analyst price targets** — anti-signal, t −3.62 to −7.21. Analyst *opinions* are refuted; analyst *coverage counts* (a neglect proxy) are a different variable and untested.
- **§20 8-K events** — selection-contaminated, needs a fixed-pre-event-eligibility design.
- **§19 LLM-as-trader** — closed externally. **§19 explicitly does NOT close LLM-as-feature-extractor**, which is what this whole section proposes.

**Nothing in the ledger closes the neglect/attention/political-connection family. It has never been tested here.**

---

## IX.5 The WRDS data — the highest-value item in this document

You mentioned undownloaded WRDS data set aside "for later." **That is the constraint that has bounded every backtest in this project since 2026-06-16.**

NEGATIVE_RESULTS §4 established that a survivorship-free universe is **not buildable on free data** — yfinance recovers 1 of 20 delisted names, and 4 of 20 return the *wrong company* via recycled ticker symbols. Every backtest number since then carries a `data_grade` stamp because of it. CANON §2 exists because of it.

**Check specifically whether your WRDS access includes:**

| Dataset | Unblocks |
|---|---|
| **CRSP** (monthly + daily stock file) | **Survivorship-free universe with delisting returns.** Kills §4 outright. This is the one that matters most |
| **Compustat Fundamentals Annual/Quarterly** | Point-in-time fundamentals with `datadate`/`rdq` — real PIT accounting data |
| **CRSP/Compustat Merged (CCM)** | The linking table. Without it the other two are much harder to use |
| **IBES** | Analyst estimates, revisions, **and coverage counts** — the neglect proxy from §IX.4 |
| **OptionMetrics IvyDB** | Would have made §27's option cohort a first-class study. Note: updates **annually**, so it is a research instrument, not a live feed |
| **RavenPack** (if licensed) | News with **event novelty and similarity-gap scores** — the exact filter from Part VIII.5 that took a Russell 2000 strategy from Sharpe 1.03 → 1.43 |
| **Audit Analytics** | Restatements, auditor changes, internal-control weaknesses |
| **Thomson/Refinitiv 13F** | Institutional ownership without the FMP quota problem |

**If you have CRSP + Compustat + CCM, the correct move is to stop everything else and rebuild the panel.** It converts the entire 179-candidate search from "direction checks on a biased universe" into real, citable, survivorship-free results — and it would let you re-run the survivors' DSR on a universe that is not itself the confound.

**Also free and worth taking immediately, regardless of WRDS:**
- **Chen & Zimmermann's Open Source Asset Pricing** — `pip install openassetpricing`. **212 predictors, 209 firm-level characteristics, data through Dec 2024, replication-verified.** Lets you test whether any new signal adds anything over 209 known characteristics. This is the "is my idea already known?" oracle, and it is free.
- **Jensen-Kelly-Pedersen ReplicationCrisis code** — a published 13-theme cluster taxonomy to use as a neutralisation basis instead of hand-rolled residualisation (which has three receipts against it: §23, §26, §27).

---

## IX.6 Honest scorecard on the thesis

| Claim | Verdict | Basis |
|---|---|---|
| "Mixing strategies beats a single strategy" | ✅ **Right** | Baltussen 222-year study; AQR 2022 |
| "Switching on market phase beats holding" | ❌ **Wrong for return, right for risk** | HMM lost 1.7pp/yr to buy-and-hold net of costs; 70% of tactical funds lag a balanced index |
| "Social/narrative bias creates durable mispricing" | ✅ **Right, and under-exploited here** | Fang-Peress, Hong-Kacperczyk, Tetlock, Hong-Lim-Stein |
| "Networks, founders, political connections matter" | ✅ **Right, and measurable** | Cohen-Frazzini-Malloy, Cooper-Gulen-Ovtchinnikov, Faccio, Acemoglu et al. |
| "Ethnic composition as a signal" | ❌ **Wrong** — bad measurement and unacceptable exposure | Use lobbying/contracts/revolving-door instead |
| "Get in early on trends" | ✅ **Right** | Da-Engelberg-Gao attention; Barber-Odean |
| "Exit at the peak" | ❌ **Refuted by your own data** | §1: sell-signal hit rate 28.6% vs 55% target |
| "LLM as a brain combined with Optimus" | ✅ **Right, as an extractor** | §19 closes LLM-as-trader only; the extraction lane is untested and legal here |
| "Lower the confidence threshold" | ⚠️ **Partly right** | Chen: t=1.79 gives FDR 1%. But your problem is power, not threshold. Use posterior sizing instead |
| "Don't depend on Sharpe; maximise ROI" | ✅ **Right objective, wrong risk** | Maximise μ − σ²/2. Take systematic risk, not idiosyncratic |
| "Take more risk to maximise ROI" | ⚠️ **Right in direction, bounded in size** | Half-Kelly ≈ 1.17× and captures 75% of max growth. Double-Kelly = zero growth |

---
# PART VII — COMPETITIVE POSITION

## VII.1 Where Aegis stands vs the open-source field

| Project | Does well | Aegis has that it lacks | It has that Aegis lacks |
|---|---|---|---|
| **QuantConnect / LEAN** | Institutional event-driven engine, live brokers, curated data | Research governance, negative-results publication, macro/crash layer | **PIT data bundles, real execution modelling, survivorship-free universes** |
| **Microsoft Qlib + RD-Agent(Q)** (NeurIPS 2025) | **The direct competitor to Aegis's autonomous R&D loop.** Multi-agent factor+model co-optimisation | **Pre-registration, placebo controls, forward paper lanes, published rejections.** RD-Agent(Q) reports only wins | Far more mature agentic search, proper factor infra, MSRA backing, peer-reviewed venue |
| **OpenBB** | Best data-plumbing layer in OSS finance (~100 providers) | Any research methodology at all | A provider-agnostic data layer Aegis arguably should adopt rather than maintain its own fetchers |
| **FinRL / FinGPT / FinRobot** | Mindshare, RL benchmarks, open financial LLMs | **Everything methodological** — these are the canonical instance of the failure mode §19 documents | Model zoo, citation volume |
| **TradingAgents** | Clean multi-agent architecture | §19 pre-emptively closed this family. A 2026 survey found **only 2 of 19 LLM-trading-agent papers reported a time-consistent train/test split** | Popularity |
| **VectorBT** | 10k parameter combos in seconds | **A brake on parameter sweeps.** VectorBT is a backtest-overfitting machine by design | Speed |
| **skfolio** | sklearn-native, **built-in CV and stress-testing of portfolio models** | — | **This is the one to adopt** — its CV-for-portfolios API is the discipline Aegis applies by hand |
| **mlfinlab** | Purged CV, triple-barrier reference implementations | Aegis reimplements and validates these — the right call given its closed-source pivot | Nothing you need anymore |

**Synthesis: the open-source field is excellent at engines and increasingly good at agentic search. It is uniformly terrible at epistemics.** Nobody publishes what didn't work, nobody pre-registers, and vectorised sweep tools industrialise overfitting. **That gap is Aegis's entire claim.**

## VII.2 What to steal from Numerai

Numerai is the strongest public example of multiple-testing-aware research design, and the design is copyable:

- **Live-only scoring.** Backtests earn nothing. ~20-business-day forward targets. This is Aegis's forward-lane philosophy, institutionalised.
- **Skin in the game.** Positive scores pay; **negative scores burn your stake.** This solves the incentive half of overfitting.
- **MMC-only payouts (since 2024).** Meta Model Contribution = covariance with the target *after neutralising to the Meta Model*. **High correlation but low originality pays nothing.**
  > **The transferable lesson: score every new candidate on its marginal contribution to the existing survivor set (gp-small, insider, fusion, TSMOM-XA), not on standalone IC.** Aegis's residualisation receipts (§26, §27) are groping toward exactly this — MMC is the clean formulation, and it would likely have short-circuited a large fraction of the 179.
- **Published performance, honestly:** 2024 was **25.45% net, 2.75 Sharpe**. **2025 was ~8% net.** One spectacular year, one ordinary year.

**Quantopian's verdict on crowd alpha is the single most relevant paper to Aegis's thesis:** Wiecki, Campbell, Lent & Stauth studied **888 algorithms with ≥6 months live out-of-sample. Backtest Sharpe predicted OOS performance with R² < 0.025.** In-sample metrics explained 1–2% of OOS behaviour; annual returns were *negatively* correlated. Higher moments (volatility, max drawdown) and construction features *did* predict. **And: the more backtesting a quant did, the wider the backtest/OOS gap.**

**QuantConnect's Alpha Streams post-mortem** is directly supportive: their submission filter *"sought strategies that perform well in all market regimes, which resulted in strong overfitting,"* and they concluded the right architecture is *"thousands or millions of smaller, focused factors."*

## VII.3 The honest bar

| Horizon | % of US large-cap active funds underperforming the S&P 500 |
|---|---|
| 1 yr (2025) | **79%** |
| 10 yr | **91.5%** |
| 15 yr | **98.1%** |
| 20 yr | **95.5%** |

**What IR 0.3–0.5 means for a $100k–$1M book at 6% tracking error:**

| | IR 0.3 | IR 0.5 |
|---|---|---|
| Alpha (gross) | 1.8%/yr | 3.0%/yr |
| **On $100k** | **$1,800/yr** | **$3,000/yr** |
| On $1M | $18,000/yr | $30,000/yr |
| **Years to t=2** | **44** | **16** |
| Years to Harvey's t=3 | 100 | 36 |

**Three consequences:**
1. **A $100k book cannot pay for its own data.** Sharadar-class PIT data at ~$2–4k/yr is 100%+ of IR-0.3 alpha on $100k. Either WRDS is free through HKU, or the economics never close.
2. **The 24-month no-skill-claim rule is right but insufficient.** 24 months of a true-IR-0.5 lane gives **t ≈ 0.71**.
3. **The deliverable that survives this arithmetic is the methodology paper, not the returns.**

## VII.4 What genuinely differentiates Aegis

Searching hard for a public comparable — a solo, open, continuously-maintained ledger of pre-registered rejections with placebo gates — turned up essentially none. The closest analogues are academic replication papers (Hou-Xue-Zhang: **65% of 452 anomalies fail at t>1.96, 82.1% at t>2.78**; Chen-Zimmermann's 212-predictor open dataset) and one defunct platform paper (Quantopian).

**The specific artifacts that impress a skeptical reader:**
- **§30 and §31 — designs killed by their own controls before their results existed.** Almost nobody builds a control that can kill their own hypothesis and *publishes it firing*.
- **§31 refuting §30's own diagnosis**, and "house 0-for-4 on family stage predictions" — self-scored forecasting on your own research process.
- **§29 labelled "NOT a negative result"** inside the negative-results file — the ledger is a chronology, not a curated defeat narrative.
- **179 trials counted.** You have the denominator. Almost no published finance paper does.

⚠️ **Where the differentiation is weaker than it feels:** an unaudited, self-maintained ledger in a repo you control is **not tamper-evident to an outsider**, however good the hash discipline. **The cheapest credibility upgrade available is an external scorer** — submit one survivor to Numerai Signals or CrunchDAO purely to obtain a third-party-timestamped forward record.

## VII.5 Publication path

1. **SSRN (Financial Economics Network)** — do this **first and immediately**, for timestamp and citability. No gatekeeping, standard practice in finance.
2. **arXiv q-fin.ST / q-fin.PM** — ⚠️ **endorsement required for a first submission**, and arXiv tightened the policy in Jan 2026. An @hku.hk address may clear it automatically; otherwise ask an HKU faculty member.
3. **Pacific-Basin Finance Journal** — runs **finance's first pre-registration publication process** (4 phases: EOI → pitch → pre-registered study plan → full study) and 55+ replication studies since 2019. **The natural home. Your ledger *is* a pre-registered study plan portfolio.**
4. **Critical Finance Review** — replication initiative, Harvey-adjacent.
5. **Journal of Financial Data Science / JPM** — the Quantopian paper landed in *Journal of Investing*; JPM published Harvey-Liu.
6. **NeurIPS/ICML Datasets & Benchmarks track** — RD-Agent(Q) landed at NeurIPS 2025 D&B. Framing Aegis's protocol + ledger as a *benchmark for honest strategy evaluation* is achievable and fast.

**What makes it publishable.** Do not write "here is my platform." Write:

> **"The survival curve of 179 pre-registered candidate signals."** Report the funnel: 179 tested → N passed explore → N passed confirm → 4 survivors. Report the deflated Sharpe of the survivors *against the full trial count*. This is a Hou-Xue-Zhang-shaped contribution on **forward, self-generated** candidates rather than published ones — and to my knowledge nobody has published that.

Secondary paper: **the placebo gate as a reusable protocol** — random-date controls that killed two of the author's own designs. Short, punchy, workshop-friendly. ⚠️ Fix F1 first, or the lead exhibit is a statistical artifact.

Engaging **Jensen-Kelly-Pedersen's "the crisis was overstated"** rebuttal explicitly is what separates a serious paper from a blog post.

---

# PART X — THE ROADMAP

Ranked by (value × probability of being right) ÷ effort. **Nothing here is "find more alpha."**

## Tier 0 — This week. Corrections that change what is true.

| # | Action | Why | Effort |
|---|---|---|---|
| **0.1** | **Re-read the §30/§31 placebo gates per-seed** (F1) and re-specify the placebo as a permutation/block-shift (F2) | May **un-close the 13D family and un-terminate the search phase**. The two firings look like a √5 artifact | 1 day |
| **0.2** | **Make the 179 counter a machine artifact**; run `evaluate_candidate` on all four survivors at n=179 (F3) | The paper's central methodological claim is currently *described but not executed*. Fixes the CANON §6 violation (registry shows 18 adoptions, 0 rejections) | 1 day |
| **0.3** | **Check WRDS entitlements** (CRSP / Compustat / CCM / IBES / OptionMetrics / RavenPack) | Potentially kills §4, the constraint on every backtest since June | 1 hour |
| **0.4** | `pip install openassetpricing` — pull the **212-predictor / 209-characteristic** dataset | The "is my idea already known?" oracle, free | 1 hour |
| **0.5** | **Verify TSMOM's first real rebalance fired** after the `451ad98` cache fix | Open verification item from the last session | 15 min |

## Tier 1 — This month. Fix what is silently broken.

| # | Action | Why |
|---|---|---|
| **1.1** | **Re-run the terminated leakage audit** | The largest known gap in this document. Its last message read *"Empirically confirmed something major."* |
| **1.2** | **Fix the D vs D−1 price asymmetry** (Part IV, defect 1) | Signals see today's close; fills use yesterday's. Look-ahead in the lane's favour, worst on ATR stops |
| **1.3** | **Wire EVENT-INTEL to a scheduled job + persist its counters** | The LLM extraction subsystem is correct, tested, and **never runs**. This is free capability already built |
| **1.4** | **Raise `daily_call_cap` from 150** | $19.96 buys ~275k extraction calls with prefix caching. The cap, not the balance, is the constraint |
| **1.5** | **Per-lane inception + n_obs on every track-record surface; suppress annualisation below 126 obs** (F6) | `−22%` over 37 days currently annualises to `−83%` in the API |
| **1.6** | **Add `P(fire \| H0)` and MDE to every registered decision rule** (F8) | **TRIAL-001 fires on noise 13–34% of the time and decides 2027-06-10** |
| **1.7** | **Make `eval_times=None` raise instead of degrading to k-fold** (F10) | CANON §8's own failure mode, inside the validation layer |
| **1.8** | **Add a position cap to the conviction lane** (Part IV, defect 4) | The lane the concentration finding is about has no cap at all |
| **1.9** | **Refresh the overdue quarterly universe** (`frozen_until: 2026-07-01`) | A month late |

## Tier 2 — This quarter. The new research direction.

| # | Action | Rationale |
|---|---|---|
| **2.1** | **Build the Tier-0 free text features** — 10-K/10-Q cosine similarity (Lazy Prices), news novelty (`1 − max cos-sim to prior 90d`), media coverage counts, analyst coverage counts | Zero cost, **zero leakage surface**, best replication record of anything in this document. Do this before any LLM work |
| **2.2** | **Pre-register NEGLECT-QUALITY**: gross profitability × low media/analyst coverage, with the interaction as the hypothesis | The synthesis of §IX.4. Backed by Fang-Peress and Hong-Lim-Stein. **Never tested here** |
| **2.3** | **Pre-register POLITICAL-ACCESS**: lobbying intensity, PAC contributions, federal contract share — free from Senate LDA, OpenSecrets, USASpending | Cooper-Gulen-Ovtchinnikov, Faccio, Acemoglu et al. **Never tested here** |
| **2.4** | **Turn on the LLM extractor properly** — closed taxonomy, temperature 0, **verbatim span citation with fuzzy n-gram validation**, self-grounding score 1–5 thresholded at 4+ | The 8-K paper's 72.6% → 96.4% precision gradient is a calibrated reliability dial |
| **2.5** | **Hand-label 300 documents yourself** | Non-negotiable under Ludwig-Mullainathan-Rambachan. Without a validation sample the LLM output is inadmissible as measurement |
| **2.6** | **Adopt MMC scoring** — every new candidate judged on marginal contribution to the 4 survivors, not standalone IC | Numerai's core lesson; would have short-circuited much of the 179 |
| **2.7** | **Implement the buy/hold spread** (buy at rank ≤40, sell only at rank >80) | Novy-Marx & Velikov: **typically halves turnover at minimal alpha cost.** The highest-ROI implementation detail available, and Aegis does not do it |

## Tier 3 — The deliverable.

| # | Action |
|---|---|
| **3.1** | **Write the paper: "The survival curve of 179 pre-registered candidate signals."** Post to SSRN immediately for timestamp |
| **3.2** | Get arXiv endorsement via HKU faculty; target Pacific-Basin Finance Journal |
| **3.3** | Submit one survivor to Numerai Signals or CrunchDAO for a **third-party-timestamped** forward record |
| **3.4** | Rewrite `ABSTRACT.md` — it describes a project that no longer exists and is the first thing an outsider reads |

## Explicitly NOT on the roadmap

- ❌ More candidate screening. The search closed at 179 for good reasons; the marginal candidate is worth less than the marginal hour of write-up.
- ❌ A multi-regime HMM driving strategy selection (68 parameters vs ~15 independent episodes).
- ❌ Options-expressed signals — the cross-sectional option family was closed by a 2025 JFE paper showing the effect is an **omitted borrow-fee artifact**; and options round-trip costs are **~13.5% of premium**.
- ❌ Real-money execution. The anti-goal stands.
- ❌ Any peak-detector. §1 is definitive.
- ❌ Ethnic/demographic screens (§IX.4).

---

# PART XI — QUESTIONS FOR CRITIQUING AGENTS

If you are an AI agent asked to review this document, these are the questions where an independent answer is most valuable. **Please state your confidence and cite sources.**

1. **F1 is the load-bearing claim of Part V.** Independently verify: does pooling 5 random-seed replicates that share an identical cohort, clustered on entry-month, inflate a cluster-robust t by ≈√5? Read `Aegis module/aegis_brain/factory/event_harvest.py:247-272`. **If F1 is wrong, the search phase stays closed and §30/§31 stand.**
2. **Should the placebo be a permutation (shuffle dates across permnos) or a circular block shift?** Which better isolates timing information from cohort selection?
3. **Is `expected_max_sharpe(179)` the right deflation for a CAR t-statistic** (§29's t=4.75), or does a different multiple-testing correction apply to event-study statistics?
4. **The leakage audit was never delivered.** Please run it: look-ahead in the research harness, FRED revised-vs-vintage (ALFRED) usage, survivorship in the ticker universe, split/dividend retroactive adjustment, PIT correctness of Form 4 filing-vs-transaction dates, and cache keys omitting inputs.
5. **Is the neglect × quality interaction (§IX.4) already in Chen-Zimmermann's 212 predictors?** If yes, what is its documented post-publication decay?
6. **What is the achievable statistical power for a political-connection signal** given that lobbying disclosures are quarterly and the cross-section of meaningful lobbyers is a few hundred firms?
7. **Challenge the Fundamental Law arithmetic in Part VI.2c.** Is TC ≈ 0.4–0.6 right for a 50-name long-only book with 4% caps, or is it higher?
8. **Is the tax finding (Part VI.2f) correct** — that a 100%-turnover taxable strategy needs 2.94% gross alpha to match buy-and-hold, roughly 2× what an IC-0.03 signal produces?
9. **What did this document miss?** Which modality was not run, which claim is unverified, which source unread?

---

# APPENDIX — DOCUMENT PROVENANCE

Compiled 2026-08-02 by a Claude Opus 5 session that dispatched 16 research agents; **9 completed, 7 were terminated by an API session limit.**

**Completed:** timeline reconstruction · negative-results ledger · capital-allocation mechanics · statistical-protocol audit · LLM-usage audit · Optimus audit · regime-switching literature · LLM-alpha literature · portfolio-construction literature · competitive landscape · options-flow literature · Chen-Zimmermann/McLean-Pontiff verification.

**Terminated before delivering — outstanding work:** ⚠️ **data-leakage audit** (the largest gap) · backtest-validity protocol checklist · alt-data/smart-money survey · congressional-trading ETF performance · short-interest data sources · emerging cheap alt-data.

All internal claims are cited to `file:line` and were read, not inferred. External claims carry URLs in the source agents' reports. Numbers marked **[DERIVED]** are arithmetic performed in this session and should be independently verified.
# PART XII — SESSION LOG 2026-08-02 & ERROR LEDGER

*This section supersedes the provenance appendix above. Written at session end, after a deliberate re-read of every prompt and response. It exists so collaborating AIs know exactly what was done, what was gotten wrong mid-session, and what the next session starts from.*

## XII.1 What this session produced

1. **This dossier** — 12 parts, built from 12 completed research agents (4 more died on an API session limit; their scopes are listed in XII.4).
2. **Three defects verified by direct computation, not agent trust:**
   - `insider_opp` = 72 PIT observations, 1 distinct value, all 0.0 → **the "insider" survivor is a constant; the survivor list is 3, not 4.**
   - `smartgrowth_pick` = 40 obs, 1 distinct value → TRIAL-SMARTGROWTH also measuring nothing.
   - `quantile_return_spread` manufactured a **+174 bp spread from a constant factor** (reproduced), reporting `status: "scored"`.
3. **C1 SHIPPED:** `engine/validation/factor_ic.py` patched — degenerate cross-sections now refused (`available: False, reason: "degenerate cross-section"`), partial degeneracy surfaced as a warning. 5 new regression tests in `backend/tests/test_factor_ic_degenerate.py`; 77 existing tests pass. **Uncommitted, in working tree.**
4. **D4 ANSWERED from the on-disk OSAP snapshot:** analyst-coverage *level* (`nanalyst`) is a documented **placebo**; coverage *decline* (`ChNAnalyst`, Scherbina 2008) is a **clear predictor**. → The neglect×quality signal must be **GP × ChNAnalyst** (quality × deteriorating coverage), not GP × coverage level. Open tension: this is a *flow* signal, and §24 found flows less tradable than levels — resolve before building.
5. **WRDS unblocked:** local `Aegis module/data/wrds_raw/` inventoried (CRSP with delistings, CCM, Compustat all present and genuine); **BoardEx extracts found truncated at exactly 500k/1M/1M rows (SQL LIMIT) with only 3,240 unique boardids in the network file — unusable for network signals until re-pulled.** `WRDS_PULL_ALL.py` written to Downloads: uncapped, count-verified, resume-safe; pulls BoardEx + IBES numest + fresh dsedelist.
6. **Lane-vs-SPY question answered:** SPY over the lane window = **+1.32%**; four lanes beat it. Today's bug fixes do **not** touch the NAV path — but the outperformers are the near-zero-beta lanes (conservative-atr bull β 0.15), so the gap is mostly *non-exposure in a flat market*, plus two still-unfixed NAV-favoring defects (D vs D−1 fill asymmetry; cost-basis marking on fetch failure). At 37 obs, SE(Sharpe) ≈ ±2.14 — no performance conclusion is possible either way.
7. **Policy agreed with Murat:** bugs in the lane path are handled the NAV-re-book way — fix ships as a **new config version → labeled segment boundary**; pre-fix history stays visible with an annotation. Never silently rewritten, never discarded.

## XII.2 Error ledger — mistakes made IN THIS SESSION, by me

Recorded because the project's own discipline (scored predictions, §26–§31) applies to the tooling too.

| # | Error | Correction | Lesson |
|---|---|---|---|
| E1 | **Relayed the audit agent's F1 conclusion unverified** — told Murat the 13D placebo gate firings were artifacts and the search phase "may reopen." Direct computation showed the seed-level t (§30: **−4.06**) is *more* extreme than the pooled −3.17 the agent attacked; the seeds agree with each other. | Corrected in-session and in Part V (F1 correction block). Standing verdict: pooling was misspecified *and unregistered* → the closure rested on an arbitrary spec choice — but the gate does **not** flip. **Do not reopen 13D.** | Verify locally-checkable arithmetic before relaying an agent's headline. |
| E2 | Dossier versions in Downloads **between builds** carried the uncorrected F1 claim for ~1 hour. | Final build corrected. Any AI that read an intermediate copy should discard its F1 takeaway. | Corrections must trigger an immediate rebuild. |
| E3 | Leakage agent claimed `quality_score` had 1 distinct value (dead). Verification: **7 distinct values per cross-section — alive.** | Caught before relay; recorded as L8b with the correction visible. | Same as E1; this one worked as intended. |
| E4 | Provenance appendix said "9 completed, 7 terminated" — 3 more agents completed later; count stale. | This section supersedes it: **12 completed**; outstanding scopes in XII.4. | — |
| E5 | Told Murat the recon script was the right 30-min move; superseded same evening by the full pull script once Duo was available. Minor whiplash. | `WRDS_PULL_ALL.py` embeds the discovery step; recon script obsolete. | — |

**Claims re-verified on re-read and standing:** survivor-list-is-three (direct SQL); +174bp fabricated spread (reproduced pre-patch, refused post-patch); FRED reference-date alignment leak (code read, not yet re-measured — C4 open); tautological `.loc[:ts]` assertions; registry = 18 adoptions/0 rejections vs CANON §6; Z(179) = 2.729 (Monte-Carlo cross-checked); SPY +1.32% over the lane window; BoardEx truncation (row counts + boardid cardinality).

## XII.3 Decisions Murat made this session

1. **WRDS pull authorized, uncapped** ("no cap download all you need").
2. **Bug-handling policy:** mark the bug, fix, segment the record — keep pre-fix history visible (XII.1 §7).
3. Confidence/risk discussion concluded: threshold-for-discovery stays high (t≥3 class); **posterior-mean sizing** governs capital; risk appetite expressed as systematic exposure (≤ ~half-Kelly), not concentration. (Part IX.)

**Still open (unmade, attended):** contamination call on the insider/smartgrowth trial clocks (restart inception vs annotate-and-continue — my recommendation: **restart**; the data is fabricated, not degraded); mirror/conviction concentration control; un-park the paper.

## XII.4 Next session — exact starting state

**First 15 minutes:**
1. Check `wrds_raw/full/pull_log.txt` — confirm no `!! MISMATCH`, BoardEx counts not round numbers.
2. Review + commit the C1 patch (`factor_ic.py` + `test_factor_ic_degenerate.py`, currently uncommitted).
3. Get Murat's contamination decision → then C2/C3 (collector fixes + `degraded` must mean `live_fetch_ok`).

**Then, in order:** C4 (FRED publication-lag map → re-run walk-forward; expect AUC/Brier to move — that re-measurement is a paper exhibit) · C5 (real leak assertions) · C6 (multifactor absent≠zero) · E1 (std of the 179 candidate Sharpes — one line, decides every survivor's deflation) · E2/E3 (machine-readable 179 counter → run `evaluate_candidate` on survivors at true N) · D2 (BoardEx→CRSP PIT linkage once pull lands; `"Curr"` sentinel = look-ahead trap) · lane-path fixes as a **new config version** (D/D−1 asymmetry, cost-basis marking).

**Research agents' brief remains Part 0.** Additional question raised by D4: is **GP × ChNAnalyst** distinct from what OSAP already documents, and does it survive §24's flow-tradability objection?

**Files:** dossier (this doc) + `AEGIS_TOMORROW.md` + `WRDS_PULL_ALL.py`, all in `C:\Users\mrthn\Downloads\`.
