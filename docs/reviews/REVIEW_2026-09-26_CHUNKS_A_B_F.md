# Review — chunks A (fast-mover forensics), B (source/actor graph), F (OpenClaw quests) — 2026-09-26

Reviewer: Opus, read-only, $0 LLM. The brief was to disagree with the builders and with
`ADJUDICATION_2026-09-26_WAVE1.md` (facts #1, #2, #9) wherever the receipts support it.
Commits reviewed: A `b827cd14`, B `54a0735e`, F `2140ba87`. Every number below was
recomputed from the files named beside it. Nothing was edited.

**RESULT IMPROVEMENT: NONE from any of the three chunks.** None of them changed a
position, a weight, or a candidate set. A and F add some gradeability. B adds none yet.

## Verdict per chunk

| chunk | terminal wealth | gradeability | verdict |
|---|---|---|---|
| **A** forensics | none | **some**: a PIT template, entry state rebuilt with the stamp column named, ex-post kept in its own column | **Keep the template, withdraw the headline.** "0 credited" comes from how the rule is built (below, W1). No strategy was tested, so no strategy was refuted. Fact #2 in the adjudication ("accepted as the honest answer") should be reopened. |
| **B** source graph | none | **none yet**: 477 rows, all n=0 | **So far a list, not a graph.** The one source class that already carries hundreds of thousands of dated, directional, gradeable claims (456 brokerages, 393,581 revision rows) was registered with n=0. Reading those claims costs $0 and was never done (W4). |
| **F** quests | none | **a little**: one dated catalyst, one numeric guidance row, 6 typed web_events | **Mostly transcript.** 26 claims, 0 with a direction, so 0 claim forecasts. About 6 of the 26 carry information the panel lacks. The promise ledger has no grading rule that can fire without another LLM card (W5). |

---

## A — "0 credited": the truth, or how the rule is built?

**How the rule is built.** `credit()` requires three things at once: `beats` (1σ_h over the
control median), `predicted`, and **`selected_for`**. Recomputed from
`fast_movers_2026-09-26.json`:

- `selected_for` is **False on 318/318 cases**, so the third condition failed every time.
  `_selected_mechanisms()` maps a book's signal to a mechanism with three regexes
  (revision / news / attention). Here is what the cases actually carry:
  - `mom_12_1`: 10 cases, no regex matches it.
  - `abstention_confidence_z`: 10 cases, no match.
  - twins (`random_genome_null`, `beta_matched_index_sleeve`): 129 cases, which return `set()` by design.
  - `why_selected.signal = None`: 111 website-lane cases, 49 fleet cases and 9 conviction cases. The reason was **never recorded**, yet the receipt prints "was not the reason it was held".
- As a result, the three ~10% books Murat named (momentum `8dbbb73b`, abstention `b109c886`,
  always-invested `3b3e7049`) **could not have been credited whatever happened.**

**The 1/5-session window.** The books entered on 2026-09-12 (a Saturday), priced at the
09-11 close, so h=5 ends 09-18. The gain landed on 09-21, which is h=6. The supplement at
h=6 shows the ±1σ bar doing its job:

- AXTI +21.9% had σ_6 = 25.6%, and it misses by 0.66pp in `8dbb` (edge +24.97% vs 25.63%).
- NUAI +28.8% had σ_6 = 19.4%.
- TWST +30.5% had σ_6 = 13.6%.

These names were running at **8–10% daily σ** (from `sigma_h`/√6). The window is the smaller
problem. The bigger one is that a monthly-rebalanced book is judged on 1 or 5 sessions.
**The window should be the book's own holding period** (to the next rebalance, or today).

**The controls.** They are 3 names from the same liquidity band and sector in the eligible
universe. That has two defects:

1. **Too noisy.** Agilent (A, +7.3% at h=5, 09-11) appears in four twin books. Its four
   control medians are **−3.6%, −3.6%, −0.2% and +0.7%**, because the seed comes from
   `case_id`. So the same event beats or misses its controls depending on the draw. MU,
   INTC and A all fell back to "sector unmapped", so large caps have no sector control.
2. **Wrong target.** Beating average stocks is factor exposure. For a rule-built book, the
   matched loser (mission rule 4) is **the same rule's next-ranked names (k+1…2k) on the
   same date**. They carry the same factor loading, so the difference is the selection itself.

**"62 favourable moves beat their controls" tells us nothing.** Cases were *selected* on
|move| ≥ 5% or ≥ 2σ, so beating a control median by 1σ is close to guaranteed by that
selection. The 62 collapse to **34 unique (ticker, entry) events**, and **43 of the 62 have
|z| < 2**: high-vol names moving by ordinary amounts. The informative denominator is
**all 1,135 positions**, not the 318 cases.

**Which of the 62 a real investor would credit:**

| event | credit to | why (receipt) |
|---|---|---|
| AXTI, NUAI, SNDK, WOLF in the momentum/abstention books (h=6) | **the RULE (12-1 momentum), as factor selection, not a stock call** | At 2026-07-31, **AXTI was held by 5 of the 10 top-sealed library rules** (`mom_12_1_liqw`, `mom_12_1_q`, `low_dtc_mom`, `resid_mom_12_1_large`, `mom_12_1_secrel`), and had been since January (`top10_for_replication_2026-09-26.json`, `held_symbols_by_date`). NUAI was held by 2 (`mom_12_1_liqw`, `mom_12_1_q`) at 06-30 and 07-31. `mom_252_21` at entry: AXTI **+2,235%**, WOLF +2,057%, SNDK +1,719%, NUAI +1,327%. The book did exactly what it was built to do. |
| MU, INTC, AMD in the website lanes, entry 2026-05-01 (+37.7% / +24.9% / +26.3% at h=5) | **partly: a revision cascade was visible at entry** | net raises over 90d at entry: MU **29 from 23 firms**, INTC 23/21, AMD 10/16. At 04-30, **MU was held by `skill_mom`, `margin_mom` and `low_dtc_mom`**. `skill_mom` is the only rule good in dev AND sealed (adjudication fact #6). MU is labelled `OTHER` because the *ex-post* lexicon found nothing, so the precursor was visible and the label hides it. |
| TWST (+30.5%, h=6) | partly | 7 net raises from 9 firms at entry. Held by **0 of the 10** top rules at 07-31. That makes it a candidate for a revision-only rule, not a momentum one. |
| A (Agilent, +7.3%) | none (twin), but a revision rule would have held it | 14 raises from 12 firms, 0 lowers, in the 90d before entry. |
| MSTR, COIN | none | crypto beta. MSTR's "visible at entry" is an **expired** 5-day forecast from 08-12 (W3). |
| GOOGL, ADBE, CRM (h=1, about +5–7%) | none | about 1–2σ, and the "visible" flag came from headline lexicon hits (W3). |
| SECZ, ABSI, ABCL, ADPT, FWDI | none, by definition | random-genome **null** twins. Their fast movers are the *base rate* the real books should be compared against, not cases to explain. |

**The class vocabulary hides the one thing that matters.** It has no `FACTOR_SELECTED`
(momentum / vol / revision rank) and no `VOL_DRAW` (|z| < 1 for the name's own σ). 89 of
318 cases have |z| < 1. So "was this name selectable the day before by a rule we own?"
cannot be expressed, and the answer (yes, for AXTI, NUAI, SNDK, WOLF and MU) never reaches
the receipt. **The full 254-rule join is still owed:** run
`strategy_library.latest_selection(panel, rule)` for every rule at the 2026-08-31 panel
date, then join to the 11 night-book names. Cost is $0, but it needs the panel build
(≈ 4 GB free today, so run it in the night window). I joined only the top-10 file above.

**Book-level check the forensics never ran.** The momentum book holds names at 8–10%/day.
With k=12 and pairwise correlation ρ≈0.3 (an assumption), the book's 6-session σ is about
16%·√(0.3+0.7/12) ≈ **10%**. A "+10% book" is then a **~1σ draw** of a very high-variance
portfolio. Before anyone explains that +10%, print the book's ex-ante σ at entry (the 63d
covariance of its 12 names).

---

## Five "you are wrong" items

### W1. "No fast mover was predicted / no strategy is credited" (A; adjudication fact #2)
**Wrong because** the credit rule could not pass for any case: `selected_for` failed 318/318.
Momentum and abstention signals have no mechanism mapping, twins select nothing, and 169
cases have no recorded reason.
**Alternative.** Give credit to the **rule**, measured against a **rank-adjacent shadow**
(the same rule's ranks k+1…2k, same date, same holding period). Add the classes
`FACTOR_SELECTED` and `VOL_DRAW`. Print `why_selected: UNRECORDED` rather than "was not the reason".
**Settling observation.** For `8dbb` (12-1 momentum, k=12), compare its return from entry
through today with the equal-weight return of ranks 13–24 on 09-11. Then repeat over all
night-book entries with date-block SEs. If held − shadow ≈ 0, the ~10% came from factor
plus variance and "luck" is the right word. If it is > 0, the selection itself earned it.

### W2. "62 favourable moves beat their controls — all accidental"
**Wrong because** the cases were chosen on the size of the move, so beating a 3-name control
median by 1σ is close to automatic. The 62 are 34 events, and 43 of them are under 2σ. The
control median for one event varies with the random draw (Agilent: −3.6% to +0.7% across
four books).
**Alternative.** Use all 1,135 positions as the denominator, at least 10 controls from the
rule-adjacent shadow, and the holding-period window. Report a **book-level z against its own
ex-ante covariance** before any per-name story.
**Settling observation.** Take the share of *all* priced positions whose holding-period
return beats their shadow, against 50%, with date-block SEs, and the same share for the 129
twin cases. If real books ≈ twins, there is nothing to explain.

### W3. "Visible at entry" (`predicted`, 57 cases) is PIT-clean
**Wrong because** `state_at_entry` filters news on `first_seen_utc` only. The corpus's
`alpaca_benzinga_news` is **36,720 of 36,720 rows published on or before 2015-02-20**. It is an
archive backfill stamped with its 2026 ingest time, so 2015 headlines ("Facebook acquiring
QuickFire Networks", a Salesforce $70 PT initiation) count as pre-entry evidence. In
yfinance, 145 of 793 rows on 09-11 are older than August. `ex_post_catalyst` *does* check
`published_utc`; `state_at_entry` does not. Separately, `_pre_seen` accepts **expired
forecasts**: MSTR is "predicted" by a 5-day forecast made 2026-08-12 and read on 09-11.
The lexicon is also broad enough that "demand", "guidance" and "contract" match most
large-cap news days.
**Alternative.** Count a news row as pre-entry only when `published_utc ∈ (t−30d, t]`.
Count a forecast only when `made_at + horizon_days ≥ entry`. Drop the benzinga archive
from any "attention" count.
**Settling observation.** Recount `predicted` under those two filters. My guess is it drops
well below 57, and that the RIGHT_STOCK_WRONG_REASON rows (ADBE/CRM/GOOGL/MSTR) mostly
disappear.

### W4. "477 sources, all n=0, weight = prior" is the correct starting state (B; adjudication fact #9)
**Wrong because** 456 of those sources are brokerages whose claims are **already on disk**.
`target_revisions.parquet` holds **393,581 dated rows from 467 firms**, and **75 firms have
≥ 20 rows in the last 12 months** (Barclays 4,260; Wells Fargo 4,093; UBS 3,786; …) with
`action` up/down and `target_action` Raises/Lowers. `seed_base_sources()` even writes
"`N dated revisions`" into each source's `notes`, then scores none of them. A registry of
n=0 rows is a list. It becomes a graph when the edges (claims → outcomes) exist, and for
brokers they could be built today for $0.
The **crowding signature** also has three defects:
1. It is unpaired. `mean(a21) − mean(a5)` comes from different claim sets once recent
   claims lack a 21d return.
2. It is noise at the threshold. For attention names at 60–90% annual vol, σ over 16
   sessions is about 15–23%, so the SE at n=10 is about 5–7% against a −1% cut.
3. It is confounded. Names that social sources talk about are high-IVOL, recent winners,
   and those reverse at 1 month *whoever* mentions them. So every social source would be
   tagged `reversal` because of what it talks about, not because of crowding.
Also: one revision row is dated **2026-10-05** (AMR/Jefferies, pulled 09-25) and still has
`pit_safe=True`.
**Alternative.**
- (a) Score brokers now: per firm and horizon, the signed 1/5/21-session return, beta-adjusted.
- (b) Build the crowding test as the **paired** signed return over sessions 6–21, minus a
  control matched on vol decile and prior-5d-return decile, and report its SE.
- (c) Refuse `event_date > pulled_at`.
**Settling observation.** Compare first-mover and follower brokers within the same
ticker-month: the first firm to raise in 30 days against the third or later. If followers
earn ~0 and first movers earn > 0, the cascade is being priced as it forms, and
`skill_mom` should weight *first* raises.

### W5. "X is walled, so every X column is NOT_READ_LOGIN_WALL" (adjudication fact #1), and the promise ledger "grades" (F)
**Wrong on X.** F read **four dated @MicronTech posts on 2026-09-26** logged out. The log
says "only public profile posts were readable". What is walled is **search** (cashtags);
**profile timelines are not**. Handle-first quests can run tonight. The caveat is that
logged-out timelines are not guaranteed to be chronological or complete.
**Wrong on promises.**
- A promise is graded only when a **later DeepSeek card** returns the *same text* with
  DELIVERED or MISSED. The grader is the model that extracted the promise, and there is
  no numeric comparison.
- The `promise:v1` forecast rows are **P(beats SPY) = 0.50**. Every outcome scores Brier
  0.25, so they grade nothing.
- The card's falsifier ("GAAP gross margin below *about* 86%") has no fixed number, so
  it cannot be graded without judgment.
- Promise 1 ("durability and predictability") names no metric.
- The MU 06-24 8-K is **not in the local `sec_edgar_8k_ex99_body` corpus** (grep: no
  Micron rows), so nothing on disk can check the guidance numbers the LLM quoted.
**Alternative.** Store promises as `{metric, basis GAAP/non-GAAP, lo, hi, unit, period, source_doc}`
and grade them with a **deterministic parser over the 09-30 EDGAR 8-K ex99.1**, fetched by
URL with no LLM. For the FQ4 promise:
- revenue ∈ [$49.0B, $51.0B]
- non-GAAP EPS ∈ [$30.00, $32.00]
- GAAP GM within ±0.5pp of 86.0% (declared now, before the print)
Alongside it, write the **priced** question: MU's 5-session return after 09-30 minus SMH,
against the options-implied move at the 09-30 close.
**Settling observation.** On 2026-10-01 the ledger holds a DELIVERED or MISSED row that no
LLM wrote. If it doesn't, the ledger does not grade.

---

## B — the minimum viable set: 10 sources gradeable within a week

"Gradeable within a week" means dated, directional, with a ticker, and resolvable at h≤5
against bars already in the panel.

| # | source | claim form | why it grades in a week | cost |
|---|---|---|---|---|
| 1–5 | **Barclays, Wells Fargo, UBS, JP Morgan, Citigroup** (the top 5 by rows in the parquet) | up/down, raises/lowers, dated | backfill: thousands of rows each, gradeable **today** at 1/5/21d; new rows resolve at h=5 inside the week | $0 |
| 6 | **SEC Form 4** open-market purchases (P code), already in `insider_events_v1.parquet` | buy = up | dated to the filing second; tens per week | $0 |
| 7 | **SEC 8-K Item 2.02** earnings releases with a guidance raise or cut (`sec_edgar_8k_ex99_body`) | guide ↑/↓ versus the prior guide | dated; the reaction resolves at h=1 | $0 parser |
| 8 | **StockTwits** symbol streams (public API; self-tagged Bullish/Bearish) | direction per message | an X substitute that needs **no login**; high volume on exactly our high-vol names; the right place to run the paired crowding test | $0 |
| 9 | **TrendForce DRAM/NAND spot** (daily session averages; already quoted by the MU card) | price Δ, a claim about MU/SNDK/WDC margins | daily; the MU−SMH residual resolves at h=5 | ~$0.01/day via OpenClaw |
| 10 | **Short-seller reports** (Muddy Waters, Citron, Fuzzy Panda, …) | down, with a named target | rare but large; historical backfill is gradeable at once | ~$0.10 once |

Drop `reddit_algotrading_rss` and `reddit_securityanalysis_rss` as *ticker* sources. On
09-11 they tagged "What do you determine as a profitable strategy?" to MSTR.

**X handles to seed by hand for our book names once login works.** Every one of these
starts `verified: false` until a dated post from it has been read. Company handles are
marketing (the four @MicronTech posts carried zero information), so seed **specialists
by sector** instead:

- **Semis / memory** (MU, SNDK, NVDA, AMD, TSM, ASML, TER, AXTI, WOLF, LITE): @dylan522p,
  @SemiAnalysis_, @Jukanlosreve (Korean memory supply chain), @TrendForce.
- **Biotech** (INCY, JAZZ, VRTX, BBIO, NTLA, ARGX, AGIO, AMGN, MRK, PRAX, COGT, KYTX,
  BHVN, ABSI, ERAS, RVMD, TWST): @adamfeuerstein, @matthewherper, @EndpointsNews,
  @FierceBiotech.
- **Tape and headline speed** (all names; these are for lead time, not direction):
  @DeItaone, @FirstSquawk, @unusual_whales.
- **Short / activist** (any name): @muddywatersre, @CitronResearch, @FuzzyPandaShort.

That is 15 handles, which is enough for n ≥ 20 per handle from a single 90-day timeline
backfill.

## F — the MU card

**Which of the twelve answers carried information not already in the price/revisions/fundamentals panel.**
The engine already has `rev_qoq 0.7375`, `gross_margin 0.8456`, `gross_margin_chg 0.1015`,
revision flow, and price.

| answer | new information? |
|---|---|
| price_volume_mix, did_they_deliver, ceo_promised | **No.** They restate the engine's rev_qoq and GM and the 06-24 release. |
| what_changed_30_90d | Partly: the 09-30 date (already on the catalyst calendar) and the WFC/Citi PT moves (already in revisions). |
| **true_now_not_modelled** | **Yes.** The **Netlist ITC 337-TA-1523** complaint (08-11, import-ban risk) is a dated, binary legal event. |
| **margin_collapse_risk / low_cost_substitute** | **Yes.** **DRAM spot** (DDR4 16Gb −0.70% on 09-24, DDR5 $57.667) and **CXMT capacity 320k→420k wafers/month by 2027**. Spot is the one *time series* here that plausibly leads MU's margin. |
| **bottleneck** | **Yes.** **2027 12-inch wafer LTA +15–25%** (TrendForce 09-25). |
| demand_product | Weak: "about 50% of revenue is data center, top-10 customers > 50%" (concentration). |
| who_benefits / who_loses | Generic; no forecast follows from it. |
| X (company / CEO / analyst) | **No.** 4 marketing posts, 0 CEO posts, 0 analyst posts. |

That is **about 4 of 12 answers carrying new information**. **26 claims for one name is
transcript, not evidence:**
- 0 have a direction, so B's `claim_rows` produced 0 forecast rows.
- 5 are marketing tweets.
- 5 come from one document (the 06-24 8-K).
- The Research Labs item appears twice.
- One is the closing price.
- There are about 8 independent documents in total.

**What I would have asked instead.** Each question is priced, thresholded, and resolved by a date:
1. What is the options-implied move for the 09-30 print, against trailing-63d σ? This is
   the magnitude prior that fact #3 says the LLM loses to. Write both and grade on 10-01.
2. What is consensus FQ1-27 revenue and GM (the *next* guide, which drives the reaction),
   and where do sell-side notes put the whisper against it?
3. What is the TrendForce Q4 contract-price forecast (%QoQ, DRAM and NAND), and how has it
   moved over the last 30 days?
4. What did SK hynix and Samsung say or pre-announce since 09-01? (Samsung's Q3 prelim
   lands in early October, a second dated check.)
5. What is the status of the Netlist ITC case: the next procedural date, and whether it
   names the 512GB RDIMM?
6. What are short interest and days-to-cover now against 30 days ago?

The falsifier should be written as a conditional with a threshold. For example: "If the
FQ1 revenue guide midpoint is below consensus, MU − SMH ≤ −5% over 5 sessions, p = 0.6."

---

## One thing to delete

**The `promise:v1` forecast rows at P = 0.50** (`thesis_card.promise_forecast_records`).
They carry no claim and score a fixed Brier of 0.25. Every one of them adds a row to
`predictions.jsonl`, the tracked, growing ledger that §64 grades, and dilutes the only
forecast population that has ever shown held-out skill. Replace them with the numeric
promise row from W5, graded by parser. The "read conditioned on status" can be computed
later from bars without writing a forecast row.

## Three ideas (cost · the observation that separates it from beta)

1. **Rank-adjacent shadow books for every rule-built position.** Cost: $0, about 1 hour of
   compute, no new data. For each rule and date, record ranks k+1…2k next to the top-k.
   **Beta separation:** the shadow has the same factor loading, so held − shadow is the
   selection itself, and the date-block mean tells us whether the rule's *sharpness* pays.
   This replaces the forensics' credit rule and also answers "was the name selectable
   yesterday".
2. **Broker first-mover skill as a `skill_mom` refinement.** Cost: $0, from the 393,581
   rows. Separate the first raise in a 30-day ticker window from follower raises.
   **Beta separation:** compare first versus third-or-later *within the same ticker-month*,
   which cancels the name's factor exposure and the market. If first movers earn more,
   `skill_net_raises_90` should be weighted by rank-in-cascade. The website lane's May
   winners (MU 29 net raises from 23 firms) are exactly the case to test on.
3. **DRAM/NAND spot as a PIT column for memory names (the Micron test).** Cost: about
   $0.01/day on OpenClaw for TrendForce's daily page, plus a one-off backfill if the
   archive is public. **Beta separation:** regress MU/SNDK/WDC's 5-session return *minus
   SMH* on the lagged 5-session spot change. The semis factor is already removed, so a
   non-zero loading is a name-specific precursor observable beforehand, which is the
   mission's rule 2 exactly.

## The first five OpenClaw quests once X is logged in

Expected information per dollar = P(changes the roadmap) × value of the decision improved ÷
cost. These are judgment calls, not measurements. Unit costs are the observed $0.004–0.025
per quest.

| # | quest | cost | P(changes roadmap) | why it ranks here |
|---|---|---|---|---|
| **1** | **Handle-timeline backfill** (90 days) for the 15 seeded specialists above. Logged-out timelines already partly work, so **start tonight** and re-run once logged in for completeness. Each dated ticker claim becomes a directional row graded at once against bars. | ~$0.30 | 0.25 | The only quest that yields **n ≥ 20 per source in one night**, which turns B from a list into a scoreboard. Best information per dollar. |
| **2** | **Pre-entry cashtag reads for winner vs matched loser.** For the 34 favourable events and 34 adverse events with a matched |z|, search `$TICKER since:entry−7d until:entry`. | ~$1.00 (68 quests) | 0.15 | Fills A's empty `x_posts` column with a *control arm*. It answers whether X attention came before the winners more than before the losers. |
| **3** | **MU 09-30 print pair.** On 09-29, `$MU (whisper OR "implied move")` plus @Jukanlosreve and @dylan522p on the FQ1 guide. On 10-01, the same search plus the EDGAR 8-K link for the parser grade. | ~$0.05 | 0.10 | The first promise that can be graded by a machine, and the first head-to-head of whisper, implied move and vol prior on one dated event. |
| **4** | **Daily top-cashtag sweep** (the 20 most-mentioned cashtags by volume, 5 sessions), with direction from post text, into the paired crowding test (W4b), run side by side with StockTwits. | ~$0.10/day, ~$0.50/week | 0.10 | The only way to learn whether the crowding and reversal labels hold up once IVOL is controlled. Otherwise every social source ends up tagged "reversal". |
| **5** | **Short-report sweep**: `from:muddywatersre OR from:CitronResearch OR from:FuzzyPandaShort` since 2025-01, with ticker, date and direction. | ~$0.10 | 0.05 | A small set with large effects that is gradeable immediately. It seeds the `down` side, which every other source here lacks. |

The five together cost about $2. The remaining budget should go to quest 1, not to more
thesis cards. One MU card cost $0.085 and produced 0 directional claims.
