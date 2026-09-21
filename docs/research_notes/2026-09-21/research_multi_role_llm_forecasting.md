# Research: multi-role LLM forecasting and market-context prompts (for chunk 23g)

Owed by roadmap §16.4 item 2. Research only — no LLM calls (paid or local), no code changes, no numbers without a source. Read first: roadmap §16.3 row 23g, §16.4 item 2, §10 (Lane X protocol), Murat's Part 1 (`feedback_murat_review_2026-09-21_morning.md`), `scripts/night_scenario_gym.py`, and `backend/data/optimus/night_factory_2026-09-21/S2_scenario_gym_run01.json`. `brain_query` returned `TRIAL-LLM-AMNESIA-1` (2026-08-08, masked/synthetic scenario machinery — predates and underlies the gym) and `docs/research_notes/2026-09-11/research_learning_loop.md` (already surveys FinCon, FinAgent, FinMem for the memory question); neither re-derived here.

## 1. What exists already — do not re-run this

- **The gym is not a single-voice reader today either.** It already runs SIX arms per case (`real`, `good_twin`, `bad_twin`, a sign-matched control for each twin, plus `control_shuffled`), each one a **committed decision** against the frozen `DECISION_SCHEMA` (`direction`, `size_pct`, `expected_return_20d`, `confidence`, `falsifier`) — `scripts/night_scenario_gym.py:186-229`. Adding roles means each arm goes from **one call to five**, not zero to five.
- **Run01 (N=300 cases, PANEL-B, Qwen2.5-7B-Instruct-Q4_K_M, temp 0, $0):** 1,800 calls, 128 directional calls (57.3% HOLD/CASH — abstention is the modal answer), sign accuracy **0.4219**, mean confidence **0.7373** (~32pp overconfidence), Brier **0.3445**, ECE **0.3154**, Brier decomposition reliability 0.0995 / **resolution 0.000407** / uncertainty 0.2439 — the model moves but essentially cannot discriminate. Movement: good-twin lift **+5.3pp** (t 4.91 vs its sign-matched control), bad-twin lift **−5.5pp** (t 2.16); headline "vs control 10.822pp". Direction-flip test (P3): **16% of cases flip** direction on one appended sentence. Adoption: `NOT_ADOPTED`, needs N≥300 **directional** decisions over ≥12 month blocks + a forward record; today's 128 directional calls over 19 blocks are short on both.
- **The gym already runs the "Alpha Illusion" P1–P6 protocol** (roadmap §10): entity masking (`night_r2_monthly_llm.widened_digests`, same function `x_anonymisation_gap` uses), a frozen date shift (±120–600 days, numbers kept verbatim), the direction-flip test AS the twin design, full frictions (25bps/side realised), and per-arm field provenance (P6). **LAP does not apply on PANEL-B** — every case postdates Qwen2.5-7B's ~2024-06 cutoff, so date-shifting makes a case un-look-up-able but not the model "younger"; PANEL-A (2015–2024) is flagged in §10 as the cheap within-panel LAP test and has not been run for the gym.
- **The analyst-snapshot ledger has one day of history** (`analyst_ledger.coverage()`: 43 rows, 43 tickers, **1 distinct day**, `revisions_possible: False`). Any brief field that reads `target_revisions()` is `MISSING` for every name today — a real constraint on §4.1, not a hypothetical one.

## 2. The literature: does giving an LLM roles help it forecast?

### 2.1 Finance-specific multi-agent frameworks

| framework | design | what it measured | how strong |
|---|---|---|---|
| **TradingAgents** (Xiao et al., arXiv:2412.20138) | Fundamental / sentiment / technical analysts, **Bull vs Bear researcher debate**, risk team, trader synthesizes | Own backtest: Sharpe **8.21** (AAPL), 6.39 (GOOGL), 5.60 (AMZN) — "above 3 = excellent"; cumulative return 26.6%/24.4%/23.2% | **Leak-prone by our own project's external check**: roadmap §10 cites "The Alpha Illusion" (arXiv:2605.16895) finding TradingAgents' Sharpe collapses **0.43 → 0.22 across the training cutoff**. Self-reported 8.21 vs cutoff-controlled 0.43→0.22 are not reconcilable — Profit Mirage in its cleanest form. |
| **FinCon** (Yu et al., NeurIPS 2024, arXiv:2407.06567) | Multi-agent, each with **layered (short/medium/long) memory + a distinct personality**, communicating to form a collective strategy; a Conceptual Verbal Reinforcement (CVRF) belief-update step | **Real ablation**: removing within-episode CVaR risk control → **negative cumulative returns, materially worse max drawdown** vs buy-and-hold; removing CVRF also degrades returns/efficiency — the one paper here with a genuine role-removed-vs-kept contrast in the expected direction | Aug 2020–Aug 2023, no visible leakage control, predates Profit-Mirage. Informative on "does structure help," silent on "is any of it forward-clean." |
| **FinAgent** (Zhang et al., KDD 2024, arXiv:2402.18485) | Tool-augmented single agent, retrieval + prompting (multimodal, not role-debate) | Already surveyed at `research_notes/2026-09-11/research_learning_loop.md:50`; cited here only to say it is not a second data point for this question | — |
| **FinMem** (Yu et al., AAAI 2024, arXiv:2311.13743) | Layered memory + one "character/profile" (risk personality), not multiple roles in one episode | Single-stock (TSLA), short window, no realistic costs — already flagged "illustrative, not evidentiary" in the 09-11 note | Its returns fall **~72%** across the training cutoff per "Profit Mirage" (arXiv:2510.07920, roadmap §10) — the sharpest leak number in the set |
| **FinRobot** (Yang et al., arXiv:2405.14767) | Four-layer **Chain-of-Thought** architecture (agents→algorithms→data ops→LLM ops), not adversarial-role debate | Descriptive platform paper — no graded forecasting accuracy, Sharpe, or Brier found anywhere | Architecture reference only; not evidence either way |

**Honest reading: no paper in this set runs a leak-controlled, cost-realistic, paired comparison of "role-debate reader" vs "single-voice reader" on a graded forecast.** TradingAgents' own number is the one directly undercut by an independent leak check; FinCon's ablation is the one real positive result and it is about **risk-management personas** (CVaR), not directional forecasting skill; FinMem and FinRobot are single-voice or non-adversarial. Rule 2 of the mission applies: this is not a finding to import, it is the gap our own gym would be first to fill — the receipt must say so, not imply the literature already settled it.

### 2.2 The general mechanism: does debate improve LLM reasoning at all?

**Du et al. (ICML 2024, arXiv:2305.14325), "Improving Factuality and Reasoning in Language Models through Multiagent Debate":** multiple instances of the same LLM independently answer, then exchange and critique each other's reasoning over several rounds before a consensus answer. Measured gains on math word problems, strategic games, factual QA vs single-agent baselines; agents "often identify and remove one another's uncertain or inconsistent facts." **This is the mechanistic argument for roles + arbitration** (an ATTACK/DEFEND pair surfacing a shaky claim the single voice would have kept) — but measured on **verifiable-answer tasks with ground truth available at debate time**, never a forecast under uncertainty, never under a scoring rule. It licenses the architecture, not a forecasting-skill number.

### 2.3 The ensemble alternative: aggregation without adversarial roles

**Halawi et al. (NeurIPS 2024, arXiv:2402.18563), "Approaching Human-Level Forecasting with Language Models":** a **retrieval-augmented, single-LM** system (search → many independent forecasts → aggregate) on 914 real forecasting-tournament questions reached **Brier 0.179 vs the human crowd's 0.149** and accuracy **71.5% vs the crowd's 77.0%** — the closest any surveyed system gets to human forecasters, via **retrieval + aggregation of independent draws**, not adversarial role-play. Our own S2 receipt shows the raw model's problem is **near-zero resolution (0.0004)** — it cannot discriminate cases yet — so Halawi's result suggests more relevant retrieved context (which the brief also is) may already move the number; 23g should be judged against "brief + N independent one-voice reads, averaged" as a second, cheaper baseline, not only against "brief + one voice, single read."

## 3. Lookahead avoidance — what each design did, and what ours does

| mechanism | what it did | what our gym already has |
|---|---|---|
| Entity/date anonymisation | Not present in any surveyed multi-agent finance paper — they run on named tickers in a fixed historical window | `night_r2_monthly_llm.widened_digests` (mask_company/tokenise) + `night_scenario_gym.shift_dates` (±120–600d, numbers verbatim) — `S2_scenario_gym_run01.json:masking` reports mask hit rate 0.4195 |
| Time-locked control model | "Alpha Illusion" P1 (adopted, roadmap §10) recommends a same-era model (e.g. ChronoGPT) as control | **Not run.** S2's P1 block: `cutoff_confidence: MEDIUM`, `time_locked_control_run: null` |
| Lookahead Propensity (L3/LAP) | "Alpha Illusion"'s own instrument | **Does not apply on PANEL-B** (`LAP.applies: false` — every case is already post-cutoff; date-shifting proves nothing about model age). PANEL-A (2015–2024, straddles the ~2024-06 cutoff) is the cheap within-panel LAP test, unbuilt for the gym. Owed before 23g's numbers can be called LAP-clean. |
| Direction-flip test | "Alpha Illusion" P3, adopted | **Run**: pass rate 0.16 at N=300. Low — keep "does the story move it" and "is the mover forecasting skill" as two separate questions in 23g's receipt. |
| Full frictions, disaggregation | P5/P6, adopted | Run: 25bps/side realised, per-field provenance table on every receipt |
| Anonymisation can destroy signal | arXiv:2511.15364, adopted as a MEASURED caveat | **Not measured by S2** — `anonymisation_gap.value_pct_pt: null` (every arm reads masked text, no raw arm to difference). X_anon_gap's own run (raw −18.89%/yr net vs masked −16.87%/yr net) is the closest measurement on disk, gap small and in the direction of masking costing less than feared, but on a different job |
| Made-up / fictional scenarios | Murat's own ask (Part 1) | This IS the twin library: `DEVELOPMENT_FAMILIES` keyed by dominant typed event, no model writes a twin (deterministic, hashed) |

None of the surveyed papers do PIT discipline at all — they backtest on named tickers in a fixed calendar window, which is exactly why the leak papers ("Profit Mirage", "Alpha Illusion") exist as a genre. **Our gym is already ahead of the finance multi-agent literature on lookahead controls**; the gap is the LAP-on-PANEL-A run and the time-locked control, not the masking/date-shift machinery, which 23g inherits unchanged.

## 4. A concrete design for 23g

### 4.1 The brief — fields and what feeds them

| field | source on disk | PIT status |
|---|---|---|
| Coverage level + breadth trend | `analyst_ledger.coverage()` / `target_revisions()['breadth_change']` | **Currently unusable**: ledger has 1 distinct day (§1); `revisions_possible: False` until a second snapshot exists. Ships as `MISSING` with a reason, never a manufactured zero — the module's own rule |
| Target dispersion + its change | `analyst_ledger._dispersion()`, `target_revisions()['dispersion_change']` | Same MISSING constraint (needs 2+ snapshots) |
| Live consensus (today-only) | `analyst_intelligence.get_analyst_intelligence()` | **Not PIT** — hits yfinance live. Usable only in the "today" arm; using it on a past-date or made-up case would be the exact lookahead 23g must guard against |
| Attention / narrative volume trend | `news_entities` masked-doc counts already computed per cell (S2 `masking.documents_in_digests`, `mask_hit_rate`) | PIT (documents dated within the cell's window only) |
| Dominant typed event | `event_vocabulary` (v3, hash pinned) via the typed-event files S2 already reads (`typed_events.coverage: 0.09` at N=300 — most cells are `no_event`) | PIT. Low coverage today (9%); receipt must say "no typed event" rather than let it read as "quiet" |
| Thematic membership (forming/growing theme) | `theme_baskets.theme_keys()` — 5 baskets (`ai_compute`, `batteries_minerals`, `energy_oil`, `pharma_biotech`, `quantum`), point-in-time via `members_as_of` | PIT by construction. Coarse binary proxy for "is a substitute forming" — not the real thing |
| **Is the market growing/shrinking; what substitute is forming** (Murat's central field) | **No source exists.** Grepped `backend/services/*.py` for `demand`, TAM, unit-shipment, substitute-tracking — none found. `thematic_momentum.momentum_12_1` is the closest cheap proxy and it is return-based, not demand-based — using it here would answer the question with the thing 23g is trying to forecast | **The real gap.** A PROBE-lane data-acquisition task (§16.2, chunk 23a) before it is a prompt-engineering one — unit shipments, capex indices, patent-filing rates, job-posting mix by technology. Recommend 23g ships WITHOUT this field first, documented as absent ("a guard derives its inputs or refuses"), and a follow-up PROBE names the acquisition |

### 4.2 Four role prompts (≤120 words each) + arbitration

All five calls answer the **same frozen `DECISION_SCHEMA`** (`direction`, `size_pct`, `expected_return_20d`, `confidence`, `falsifier`) — the roadmap's own instruction ("each answers the frozen schema; a fifth call arbitrates"), so no new taxonomy and no new parser.

- **ATTACK** (bear): *"You are the ATTACK analyst. Given the brief, argue the strongest case AGAINST this company's next 20 sessions: what substitute or structural threat is forming, where coverage/dispersion is already souring. Commit to your own decision — do not soften it into HOLD unless the brief truly gives you nothing to attack. State the one fact that would prove your attack wrong as `falsifier`."*
- **RESEARCH** (neutral): *"You are the RESEARCH analyst. Read only the brief's factual fields — coverage, dispersion, typed event, theme membership. State the base rate: what has historically happened to names with this profile, without taking a side. If the brief gives no signal, your direction is HOLD or CASH — that is correct, not a failure."*
- **DEFEND** (bull): *"You are the DEFEND analyst. Argue the strongest case FOR this company holding or growing its position: why the substitute named in the brief is not yet a real threat, why coverage/dispersion still supports it. Commit to your own decision. State the one fact that would prove your defence wrong as `falsifier`."*
- **ALTERNATIVE**: *"You are the ALTERNATIVE analyst. The other three debate this company directly. Your job: is there a BETTER-positioned name implied by the same brief — the substitute itself, a supplier, a low-attention beneficiary of the same trend? Your `direction`/`size_pct` apply to THIS company only, but your `falsifier` must name the alternative you'd rather hold instead."*
- **ARBITRATE** (5th call, sees the brief + all four JSON decisions): *"You are the ARBITRATOR. Four analysts have each committed a decision on the same brief. Where they agree, that is not four independent votes — they read the same brief. Where they disagree, that disagreement is itself information. Produce the FINAL decision. Your `falsifier` must name which analyst's case would have to be wrong for your decision to be wrong."*

The ARBITRATE prompt's "agreement isn't four independent votes" line is deliberate — the cheapest guard against the failure Halawi's crowd-comparison implies: if the four roles just restate the brief in four voices, the arbiter should not read apparent unanimity as higher confidence. This is also the seed of chunk 23f (forecast-error correlation); nothing to build now, just don't foreclose it.

### 4.3 Evaluation design

**Two orthogonal ablations, both paired on the SAME cases (same masked, date-shifted brief), same six-arm/twin structure kept unchanged:**

|  | no brief (today's prompt) | with brief |
|---|---|---|
| one-voice | existing S2 run01 (N=300, already on disk) | new: 1 call/case |
| four-role + arbitrate | new: 5 calls/case | new: 5 calls/case |

Primary reads: (a) four-role vs one-voice sign accuracy and Brier, **paired, brief held constant** (the roadmap's own ask); (b) brief vs no-brief, one-voice held constant (the ablation). Both differences are computed on the SAME case set, so date/regime shocks hitting both arms of a pair cancel — unlike the return-mean tests (canon §58, block-dependent), a **paired** sign-accuracy or Brier difference is not obviously block-limited, but the within-case correlation between arms (ρ) has never been measured on this gym and the receipt must report it rather than assume it.

**Minimum n, conservative (ρ unmeasured, treated as 0 — an upper bound, not a size to run blind):** for a **5pp** sign-accuracy difference at two-sided 5% / 80% power, using the same constant the gym's own `mde()` uses (`2.8 = z_.025 + z_.80`) and `p=0.5` (max-variance case): `n = 2 × p(1−p) × 2.8² / δ² = 2 × 0.25 × 7.84 / 0.0025 ≈ 1,568` directional decisions **per condition**. At run01's directional-call rate (128/300 = 42.7%), that is **≈3,670 cases per condition** — about **12× today's N=300** — before correlation is accounted for. Positive correlation (likely, since both conditions read the identical brief) would cut this substantially, by an unmeasured amount. **Recommended first step: run the paired design at N=300 (today's existing cell count) to MEASURE ρ and the discordant-pair rate before pre-registering a larger N** — the same "measure before committing scale" pattern used elsewhere (VOI, chunk 23e).

**Cost per case:** today's run is 6 arms × 1 call = 6 calls/case (1,800 calls at N=300, S2's own headline). Four-role makes every arm 4 roles + 1 arbiter = **5 calls instead of 1**, so a full four-role run is **30 calls/case — a flat 5× today's** (holds whether roles are added to all six arms or just `real`, since 6×5 = 5×6). At Qwen2.5-7B's measured throughput from run01 (1,800 calls in 2,144.9s ≈ 1.19s/call), a 300-case four-role run is ≈9,000 calls ≈ **~3 hours** — longer than the 90-minute night-queue box (`SCENARIO_GYM_BOX_MINUTES`). **First informative read should target N≈100 cases** (3,000 calls, ≈60 min, fits one box), not N=300, with the full-scale run following once ρ is measured and the box or queue slot is widened.

## 5. What would kill it

**HYPOTHESIS_KILLED** if, at whatever N the paired read reaches power: four-role sign accuracy and Brier are statistically indistinguishable from one-voice (with or without the brief), **and** the arbiter's final answer is recoverable by simple majority vote over the four roles' raw directions (the arbitration call adds nothing the roles didn't already vote) — that would mean roles add disagreement-flavoured noise around the same underlying single judgment, not new information, exactly the "unanimous correlated votes count once" trap Murat's review names. A **weaker but real partial kill**: if brief-alone (one-voice, with brief) already captures most of the improvement over no-brief, and four-role adds nothing further — the value is in context (Halawi's retrieval result, §2.3), not roles, and 23g should ship the cheap half only. Either result is a receipt, not a failure — per §16.1 the chunk closes on `BELIEF_CHANGED` (numbers before/after) even when `HYPOTHESIS_KILLED` is the roles-add-nothing branch.

## 6. Ten-line summary

1. No finance multi-agent paper runs a leak-controlled, paired role-vs-voice forecast comparison — a gap our gym would fill, not a result to import.
2. TradingAgents' self-reported Sharpe (8.21) is directly undercut by an independent leak check (0.43→0.22 across the cutoff) — the sharpest Profit-Mirage instance in the set.
3. FinCon's CVaR ablation is the one real memory/role-removed-vs-kept result, and it is about risk framing, not directional skill.
4. Du et al. (general debate) supplies the mechanism (agents catch each other's unsupported claims) but was measured on verifiable tasks, not forecasts.
5. Halawi et al. shows retrieval + aggregation of independent one-voice reads gets an LLM to Brier 0.179 vs the human crowd's 0.149 — the cheap alternative baseline 23g should also run.
6. Our gym already implements the Alpha-Illusion P1–P6 protocol except the time-locked control and LAP-on-PANEL-A; roles inherit that, not rebuild it.
7. The brief's headline field (growing/shrinking, forming substitute) has NO data source on disk today — theme-basket membership is the nearest proxy and it is coarse; ship the brief honestly missing that field rather than fabricate it.
8. Four roles + one arbiter, same frozen `DECISION_SCHEMA`, ARBITRATE told explicitly that agreement isn't four independent votes.
9. Cost is a flat 5× today's calls (30 vs 6 per case); a 300-case four-role run doesn't fit the 90-minute box — start at N≈100.
10. Minimum n for a clean 5pp paired difference is ≈3,670 cases unpaired-conservative (~12× today's N); measure the within-case correlation at N=300 first rather than pre-registering the larger N blind.
