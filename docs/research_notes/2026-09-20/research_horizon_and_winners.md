# RESEARCH — horizon (day trading vs holding) and what winners say, 2026-09-20

Murat's question, verbatim: *"if it makes more money u can try day traiding but if
holding for months is better thats better search this and see what people that won
in markets are saying find correlations between things"* — plus candidate sources:
SP1/SP3, analyst-target-influenced buys, trackings, politicians, Polymarket, Trump,
demand. Sonnet research only; no LLM-API or order-placing script was run. Licence:
`PRODUCT_EXPERIMENT`-scoped reading — nothing here is a claim.

---

## 1. HORIZON — what the evidence says, net of costs

**Academic, retail day trading.** Barber & Odean's Taiwan study (3.7bn transactions,
1992-2006): day traders lost **23.9 bps/day net of fees**, aggregate performance
negative in 14 of 15 years; only ~1% of day traders are predictably profitable
after fees ([Barber, Lee, Liu, Odean, "Do Day Traders Rationally Learn About Their
Ability?"](https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trading%20and%20Learning%20110217.pdf)).
Brazil, Chague/De-Losso/Giovannetti, 19,646 futures day traders 2013-2017: of the
1,551 who persisted >300 days, **97% lost money net of fees**, 0.5% earned more
than a bank teller ([SSRN 3423101](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101)).
Barber & Odean's original "Trading Is Hazardous to Your Wealth" (66,465 households,
1991-96): highest-turnover quintile earned 11.4%/yr vs 17.9%/yr market; gross
returns were similar across groups, **all the destruction is post-cost** —
overconfidence drives excess turnover
([JF 2000, PDF](https://faculty.haas.berkeley.edu/odean/papers%20current%20versions/individual_investor_performance_final.pdf)).
**SPIVA** (systematic, not retail, but the same horizon question): over the 15
years to Dec-2024, ~88-92% of active US large-cap managers underperformed the S&P
500 net of fees, and **zero of 22 US equity categories** had a majority of active
managers beat their benchmark over 15 years
([S&P SPIVA US Year-End 2024/2025](https://www.spglobal.com/spdji/en/spiva/article/spiva-us/)).
All three literatures point the same way: **shortening the holding period raises
gross turnover and cost drag faster than it raises the odds of being right**, and
the effect compounds — the loss is concentrated in the tail of very-high-turnover
accounts.

**Practitioner.** Renaissance's Medallion is the standard "but RenTec is
short-horizon" counter-example: reported ~150,000-300,000 trades/day, holding
periods often ~2 days, edge described by staff as "profitable only slightly more
often than not" at 2014 Senate testimony
([LuxAlgo summary](https://www.luxalgo.com/blog/simons-strategies-renaissance-trading-unpacked/)).
That edge required proprietary infrastructure, colocated execution, and leverage a
solo operator cannot replicate — it is not evidence that short-horizon trading
works for a retail-cost account; it is evidence that short-horizon trading works
**only** with an execution/cost structure retail does not have. Every long-run
practitioner whose letters are public (§2) instead describes holding periods of
months to years and explicitly warns against activity-for-its-own-sake (Marks:
"the greatest risk arises when investors believe there is no risk" and the case for
patience over action —
[Oaktree memos](https://wyandanchlibrary.com/read/marks-oaktree-memos)).

**Verdict for a solo operator at ~$100k paper books, ~25 bps/side realistic cost:**
day trading is a **cost-arithmetic loser by default** — one round-trip per name
per day for 250 sessions is 125 points of annual drag before any edge, against
evidence that 95%+ of persistent retail day traders never clear that bar net of
*lower* costs. Multi-week/multi-month holding is the evidence-favoured horizon
without RenTec's execution stack. **This matches where our own evidence sits**:
`NEGATIVE_RESULTS.md` §1 killed the timing-signal engine vs buy-and-hold; §9/§10
killed monthly-cadence momentum on risk grounds (17.9% CAGR beat SPY's 15.3% but
a -54.7% max DD made it uninvestable; a trend-filter rescue made it *worse*,
-61.3% DD); the one registered **positive** book, Book F calendar seasonality, is
**monthly-rebalanced** (+0.43%/mo net vs twin at the $10M floor, t 3.12,
`backend/data/optimus/night_factory_2026-09-13/B_books_efg_replay_run01.json`,
per `docs/AEGIS_CONTEXT_DOSSIER_2026-09-19.md` §3). The one tested *intraday*
mechanism, buy-close/sell-open (`docs/FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`),
confirmed the anomaly is real (10.73 bps/day overnight, t 8.71) but returned
`ANOMALY_CONFIRMED / STRATEGY_REJECTED` — no book was licensed; the only adopted
residue is a defensive **execution rule** (reduce exposure intraday, never hold
overnight short into the open, per `research_murat_ideas_adjudicated.md`).
**Do not re-propose day trading or overnight holding as a standalone book** —
both are closed to this question. The 30-minute-cadence book (lane D,
`docs/AEGIS_VISION_2026-08-28...`) is an infrastructure/venue check, not a
signal test, and carries a stated **low prior**.

---

## 2. WHAT WINNERS SAY — 8-12 decision rules as testable hypotheses

1. **Concentrate on high-conviction ideas rather than diversify broadly**
   (Druckenmiller — [thehustle.co](https://thehustle.co/stanley-druckenmiller-q-and-a-trung-phanin)).
   **TESTABLE_NOW**: rank the composite by conviction percentile, compare a
   top-5 book to the top-50 book at equal costs — exactly what
   `TRIAL-DRAFT-KELLY-CONSTRUCTION-v2` and `ce_kelly` vs EW (`arena/policies.py`)
   already measure; read that receipt before re-registering.

2. **Cut losses fast, let winners run** (Druckenmiller/Soros pound trade).
   **TESTABLE_NOW**: kill-condition asymmetry exists in
   `investment_committee.compose_book`; test whether trailing past the original
   target beats a fixed-target exit, net of costs, on the CRSP panel.

3. **Second-level thinking — an edge requires being right AND different from
   consensus** (Marks —
   [worldlyinvest.com](https://www.worldlyinvest.com/p/howard-marks-on-the-power-of-second)).
   **TESTABLE_NOW**: does the analyst-target anti-signal (§17,
   TRIAL-TGT-REBUILD) strengthen when the position is also crowded (high
   institutional ownership, §26 data)? A consensus-divergence interaction is a
   concrete regression on files we hold.

4. **Risk is probability of permanent capital loss, not volatility** (Marks).
   **NOT_A_HYPOTHESIS as stated** — a definitional stance. Derivative: does a
   drawdown-kill rule beat vol-targeting net of costs? §21 (INSTR-COND-VT)
   already tested vol targeting and it died in the 2020 crash — **CLOSED**,
   cite §21 before re-registering.

5. **Believability-weight information by track record, not confidence**
   (Dalio — [principles.com](https://www.principles.com/principles/633d5d13-8610-425f-ad62-cd62347d9165/)).
   **TESTABLE_NOW**: weight analyst/insider signals by the *submitter's*
   historical hit rate rather than treating all filers equally — the raw
   histories to compute a per-source track record already exist.

6. **Pain + reflection = progress — grade every decision against its
   outcome** (Dalio; also CLAUDE.md rule 4). **ACCRUING_ALREADY**: the Decision
   Contract / decision-vs-reality loop shipped 2026-09-19 (roadmap §14.4
   chunk 18); read the ledger once it has rows, no new hypothesis needed.

7. **Margin of safety — buy meaningfully below a conservative value estimate**
   (Klarman). **NEEDS_DATA**: requires a PIT intrinsic-value pipeline (DCF or
   multiple-based) — we hold the Compustat/CRSP inputs but no valuation model
   is built; a build gap, not a closed result.

8. **Reflexivity — crowded narratives can be self-fulfilling until they
   revert violently** (Soros). **NEEDS_DATA/partial**: the typed-event
   vocabulary plus text-return panel could test whether sentiment extremes
   predict *reversal* magnitude — but E1's typed-event arm already lost to its
   shuffle control at 20k headlines
   (`docs/HANDOFF_2026-09-11_FABLE_TO_OPUS_BUILD_PLAN.md`) — read that first.

9. **Circle of competence — own what you understand** (Buffett/Munger,
   [Berkshire letters](https://www.berkshirehathaway.com/letters/letters.html)).
   **NOT_A_HYPOTHESIS as stated** (no "understanding" variable exists);
   derivative is coverage-normalised confidence — does restricting the
   universe to dense-coverage names change hit rate? This is the VISION file's
   "coverage normalisation" idea.

10. **Best ideas concentrated inside a diversified book beat a pure
    concentrated book** (Antón/Cohen/Polk +2.8-4.5%/yr and Petajisto +1.26%/yr
    net, both measured *inside* diversified funds — `docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md`
    line 1317, vs Janus Twenty -69% and ARK -48%/$14.3bn destroyed).
    **TESTABLE_NOW**: compare top-decile names held inside a 100+ name book vs
    a concentrated 10-stock book, same costs.

11. **Time horizon is a chosen edge, not a constraint** — Buffett and RenTec
    sit at opposite extremes, each working only inside its own cost/information
    structure. **NOT_A_HYPOTHESIS as a single test** — frames §1's verdict; the
    derivative is the holding-period sweep already run there.

12. **Buy the disclosed intent, not the raw stake** (confirmed by §29: 13D
    "activist" filings move price at +1..+20, +120.7bps t 3.38; 13G "passive"
    filings at the same 5% threshold do not, +9.7bps t 1.64 — **declared
    intent carries the number**). **ACCRUING** as roadmap chunk 21 (13D
    event-window book with 13G placebo).

---

## 3. MURAT'S SOURCES

| Source | Verdict | Evidence |
|---|---|---|
| **Analyst price-target-influenced buys** | **CLOSED (§17)** | TRIAL-TGT-REBUILD: raw 12m-upside consensus is an **anti-signal** — largemid −90bps/mo net (t −3.62), small −199bps/mo (t −7.21); PSZ-2025 low-dispersion conditioning halves the bleed but never turns positive (IC t −3.77). Do not re-register naive target-upside. |
| **Politicians (Congress trades)** | **ACCRUING_ALREADY** | `TRIAL-CONGRESS-IC` live, decision 2027-01-11 (`docs/TRIALS/TRIAL-CONGRESS-IC.md`). Literature mixed-to-negative unconditionally: Eggers & Hainmueller ([SSRN 1762019](https://ssrn.com/abstract=1762019)) find mediocre 2004-08 performance; Belmont et al. ([NBER w26975](https://www.nber.org/papers/w26975)) find senators' purchases **underperform** industry/size peers by 11-28bps at 1-6mo, no committee skill. `docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md` line 1561 flags the upgrade: **condition on leadership status** (Wei & Zhou) — the trial currently scores unconditionally, the null specification. |
| **Polymarket / prediction markets** | **TESTABLE_NOW (sensor, not trade)** | Collected daily already (`dataflows/polymarket.py`). `docs/ADJUDICATION_2026-08-21_PREDICTION_MARKETS.md`: cross-venue arb real but fee-eaten; open question is **divergence measurement** as a regime sensor, registered not adjudicated — no result licenses it as a stock-selection signal. |
| **Trump-policy-driven moves** | **CLOSED as a trade, OPEN as an event class** | `research_murat_ideas_adjudicated.md` line 170 and the CXMT/Micron read: MU's −5.2% on 09-14 was a **sector-wide day**, not Trump-specific ("obvious in hindsight is not a signal," `docs/research/CAUSAL_BRAIN_RESEARCH_2026-07-28.md`). Residue: a missing event class, `foreign_entrant_capacity`, registered `TRIAL-DRAFT-FOREIGN-ENTRANT-IC-v0.md` — test the class, not "Trump" as a ticker bet. |
| **Demand (search trends, app downloads, web traffic)** | **NEEDS_DATA / partially CLOSED** | Google Trends kept as a niche tilt only (`pytrends` fragile, SVI repaints — look-ahead risk), `docs/GATE_M_RESEARCH_VERDICTS_2026-08-04.md` line 108. App downloads/job postings/web traffic **skipped** — paid data exceeds a solo budget (`docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md` line 1571). Our own hiring collector (192/2,362 names, Greenhouse/Lever/Ashby) is a live, free demand proxy already collecting. |
| **"Trackings" (following named investors / 13F clones)** | **CLOSED (§26, generic) / mixed literature** | Eight in-house 13F variants dead, same signature — real rank, dead book (`docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md` line 1555); §26 killed abnormal IO (small-cap IC t=11.29, net t −0.14 after the 45-day lag), and §28 found the information sits in the **short leg** (99.9% of the spread). Live evidence: GURU's 14-year mediocre record, ARK destroyed ~$14bn. Surviving thread: best-ideas cloning **inside** a diversified book (rule #10) — a construction question, not tracking. TRIAL-ARK-IC separately live. |
| **"SP1 SP3"** | **UNRESOLVED — grepped, not found.** Searched `docs/`, `NEGATIVE_RESULTS.md`, `docs/TRIALS/` for `SP1/SP3/SP-1/SP-3/sp_1/sp_3` — only unrelated near-matches (a refactor stage-naming "S1/S3-S8", regime labels s0-s3). Web search for an ORB/ICT setup named SP1/SP3 found nothing specific. **Best two readings**: (1) SPY/S&P index legs from external course material; (2) "Setup 1/Setup 3" from a retail day-trading course. Ask Murat for the source before spending research time — same pattern as the unresolved "Xfield" URL in roadmap §14.5. |

---

## 4. CORRELATIONS — 6 concrete tests, with files and controls

1. **Insider cluster buys × analyst-revision direction × forward 60d return.**
   Files: Form-4 bulk (`docs/AEGIS_CONTEXT_DOSSIER_2026-09-19.md` §7, WRDS Form 4
   bulk; `sec_insider_bulk_load.py`) × analyst snapshots
   (`backend/data/optimus/analyst_snapshots/*.parquet`, `analyst_snapshot.py`,
   `revision_forecaster_v1.py`) × CRSP PIT
   (`backend/data/optimus/crsp_pit/crsp_pit_monthly_v1.parquet`). Literature
   prior: cluster buys ~2x single-insider excess return over 21 trading days
   (Lakonishok & Lee 2001, replication caveats noted — cluster alpha has
   compressed on recent data per practitioner summaries). **Null/control**: a
   shuffled-ticker placebo (same-date, random-ticker insider "buys") plus the
   existing 13D/13G-style declared-intent control — since §46 (N1) already found
   insider return does **not** accrue *before* disclosure on five filing days,
   the interaction test must condition on *post*-disclosure drift only.

2. **13D activist-intent filings × sector ETF flow direction × abnormal
   return.** Files: the already-cleared §29 13D/13G event table
   (`backend/data/optimus/events/event_table_v1.parquet`) × sector rotation /
   ETF flow service (`backend/services/sector_rotation.py`,
   `backend/data/optimus/text_return_panel/` for the return panel). **Control**:
   the existing 13G placebo (same threshold, differing declared intent) as the
   primary control, plus a random-date sector-flow draw as the secondary null.

3. **Typed-event class (event_vocabulary.py's 39 ids) × sector co-movement ×
   next-day sector-relative return.** Files:
   `backend/services/event_vocabulary.py` (the 39-id table) ×
   `backend/data/optimus/text_return_panel/news_returns_2025_26.parquet` ×
   `backend/data/optimus/event_response/event_panel_cache.parquet`. **Caveat
   read first**: E1's typed-event scalar arm already lost to its own
   capacity-matched shuffle control at 20,000 headlines
   (`docs/HANDOFF_2026-09-11_FABLE_TO_OPUS_BUILD_PLAN.md`, "the remaining 143,000
   headlines are NOT typed") — this correlation should be scoped to the classes
   with the strongest documented priors (e.g. `bankruptcy_or_going_concern`,
   `growth_constraint_cited`) rather than the full 39-way cross, and must carry
   the SCALAR_SHUFFLE control from day one.

4. **Congressional trade direction × leadership status × forward return** (the
   dossier's own flagged upgrade). Files: `TRIAL-CONGRESS-IC` snapshot table
   (`docs/TRIALS/TRIAL-CONGRESS-IC.md` names the collector) × a leadership
   roster (public, point-in-time reconstructable — committee-chair and
   party-leadership lists by Congress session) × CRSP PIT returns. **Control**:
   non-leadership members' trades as the internal control arm — the design Wei
   & Zhou's critique implies, run inside the already-accruing trial rather than
   as a new registration.

5. **Abnormal institutional ownership short leg (§28's 99.9%-in-the-short
   finding) × analyst-target anti-signal (§17) as a joint exclusion screen on
   Book F.** Files: `io_level`/`io_abn` ranks (per
   `docs/HANDOFF_2026-09-11_FABLE_TO_OPUS_BUILD_PLAN.md`'s `B_exclusion_screen`
   job, `scripts/night_b_exclusion_screen.py`) × target-upside ranks
   (`scripts/analyst_target_grades.py`) × Book F's monthly seasonality replay
   (`backend/data/optimus/night_factory_2026-09-13/B_books_efg_replay_run01.json`).
   **Control**: the random-exclusion twin already built into
   `night_b_exclusion_screen.py` (same count, re-drawn per floor) — reuse it
   rather than inventing a new null; Holm-correct the screened vs random-exclusion
   contrast per the existing discipline, not screened vs unscreened.

6. **Google Trends attention acceleration × news-count acceleration (GDELT) ×
   forward variance/skew (not price direction).** Files:
   `trends_sentiment.py` (Google Trends fear/greed) × GDELT counts (news_pull
   registry) × OptionMetrics-derived skew features
   (`learner/features_options.parquet`, per the exclusion-screen job's own skew
   inputs). This is the defensible version of the NVDA/TSLA-attention thesis
   already scoped in `docs/AI_REVIEWS_SYNTHESIS_2026-08-03.md` line 75 — the
   claim is variance/vol prediction, explicitly **not** reversal timing (our own
   §1 killed peak-detection at a 28.6% hit rate). **Null**: acceleration adds
   nothing beyond plain momentum — the prereg's own stated null.

---

## 5. TOP-5 to backtest first, ranked by expected information per hour of compute

1. **Congressional leadership-conditioning (item 4 above).** One-line
   construction: split `TRIAL-CONGRESS-IC`'s already-accruing snapshot table by
   leadership-vs-non-leadership at trade date, compare forward 21/63/126d rank-IC
   between the two subgroups. Cheapest possible test — no new collector, no new
   registration, reuses a live trial's own data; directly answers a
   literature-flagged, already-adjudicated upgrade.

2. **§28/§17 joint exclusion screen on Book F (item 5 above).** One-line
   construction: intersect the `io_abn`/`io_level` worst-decile exclusion with
   the analyst-target worst-decile exclusion, apply both to Book F's pool before
   selection, compare against the existing random-exclusion twin already coded in
   `night_b_exclusion_screen.py`. Reuses the one book with a positive registered
   read; adds nothing new to build, only a second screen on top of chunk-19's
   first.

3. **13D-intent × sector-flow interaction (item 2 above).** One-line
   construction: on the already-cleared 13D event table, bucket by whether the
   filer's sector ETF had positive or negative 5-day flow at filing, compare CAR
   at +1..+20 across buckets, holding the 13G placebo as the joint control.
   Reuses a cleared, placebo-confirmed positive family (§29) — high prior,
   cheap to run before chunk 21's fuller book build.

4. **Insider cluster-buy × post-disclosure drift, conditioned on cluster size
   (item 1 above, post-disclosure only).** One-line construction: on the Form-4
   bulk table, define cluster = 3+ distinct insiders buying within a 5-day
   window, compare 21/63d forward return of cluster vs single-insider buys,
   post-disclosure date only (per §46's precursor timing lesson), against a
   shuffled-ticker placebo. Directly tests a literature-cited, compressed-but-
   not-dead effect; moderate build cost (cluster-detection logic on data already
   held).

5. **Trends/GDELT acceleration → forward variance (item 6 above), scoped to
   the existing OptionMetrics skew panel.** One-line construction: regress
   30-day-forward realized-vol change on trends-acceleration + GDELT-count-
   acceleration, controlling for momentum, on the panel §52 (N6) already proved
   has second-moment predictability. Highest build cost of the five (needs the
   Trends/GDELT join done carefully re: SVI repainting look-ahead), but tests a
   mechanism our own §52 result already says is real and free — the payoff is a
   second confirming leg on the programme's one clean positive finding, not a
   fishing expedition.

