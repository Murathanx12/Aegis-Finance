# ROADMAP 2026-08-29 — WEEKEND TO MONDAY OPEN (the ONE current roadmap)

**Status:** TIER 1. Supersedes `ROADMAP_2026-08-26_HUMAN_HEURISTICS_AND_FAST_RESEARCH.md`
for the window Sat 29 Aug → Mon 31 Aug 21:30 SGT / 09:30 ET, and ABSORBS the
GPT-authored `docs/ACTIVE_ROADMAP.md`, which sits UNMERGED on branch
`origin/docs/canonical-integration-20260828` (commit d4bde9f). Merge that
branch, then keep THIS file as the index entry — one roadmap at a time.
**Builder:** Opus. **Overseer / red team:** Fable. **Decider:** Murat.
Strategic authority stays `AEGIS_STRATEGIC_INVARIANTS.md` + `AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`.

---

## 0. RESULTS SCOREBOARD (read from the venue at 13:30 SGT Sat, not from logs)

**RESULT IMPROVEMENT: NONE.** Friday was the first live session; every number
below is a measurement, not a verdict.

| role | mandate | equity Sat | day 1 | open positions | what it did |
|---|---|---:|---:|---|---|
| hack1 ANCHOR | conservative, index+NVDA | $99,250 | −0.75% | 0 | NVDA 110sh @226.81 09:30 → stop 220.00 at **09:36** |
| hack2 DRIFT | aggressive, drift | $99,239 | −0.76% | 0 | NVDA 110sh @226.71 → stop 219.79 at 09:37 |
| hack3 THESIS | basket | **$91,107** | **−8.9%** | BE 116sh (−$416) | 12 names bought 09:30:47–09:31:00, **eleven stopped 09:36–09:48** |
| hack4 PREDATOR | maximum | $99,080 | −0.92% | NVDA 113sh | NVDA 217.5/210 put spread ×6 @0.82cr; legs closed 13:03/13:08 ET (−$0.8k); re-entered shares 13:23 |
| hack5 CONVEXITY | convex, options only | **$91,419** | **−8.6%** | BE 190C ×2 (−$960), PLUG 2C ×80 (−$720) | five Sep-4 OTM calls; NVDA/SMR/QS closed at −60%/−60%/−63% |
| hack6 BLEND | aggressive, council | **$90,706** | **−9.3%** | 0 | 14 names 09:32–09:33; **13 stopped 09:33–09:43**; DKNG exited **+2.5%** at 13:05 (measured target hit) |

Independent selectors trading: 3 (drift, basket, convex). Farm candidates: 0
promoted. External drag: opening-minute fills on 100%-vol names (BE 214.36 →
stop 211.23 on hack6, 217.78 entry on hack6 vs 214.36 on hack3 — the two
basket books paid different opening prints for the same idea).
LLM spend: unchanged (~$3.7/day DeepSeek); first Featherless-only digest run
this session (§7).

## 1. WHAT ACTUALLY HAPPENED — the arithmetic the reviews missed

The GPT review says "twelve tickers, one bet" and "convexity failure". Both
true, both second-order. The first-order cause is **LEVERAGE**, and it is
still in the code:

- `alpha/runner.py:contracts_for` converts a RISK fraction to shares as
  `risk × equity / (spot × charge)`, then caps at
  `equity.MAX_NOTIONAL_FRACTION = 0.25` **per name**. There is **no gross
  cap** (`grep gross alpha/admission.py` → nothing). Twelve admitted names ×
  25% = **300% gross**, which Alpaca paper margin allows. Every basket fill
  on Friday was ≈$25k on a $100k book (QUBT 2,922×8.55, IONQ 600×41.2, BE
  116×214, …). hack6 held **fourteen** = 350% gross.
- Realised loss = gross × stop = 3.0 × 3% ≈ **−9%**. That is the whole
  number. Correlation decided that all twelve fired instead of six; leverage
  decided that each firing cost 0.75% of the book instead of 0.09%.
- **The Friday-night fix does not do what its commit says.** afa77c9 set
  basket `per_thesis 0.03 / aggregate 0.36` and stop 8%, claiming worst case
  ≈ −2.9%. Recompute: charge ≈ 8% stop + ~3% gap = 11%; notional = 3%/11% =
  27% → capped **25%, unchanged**; admission sums max_loss = 12 × 25% × 11% =
  33% < 36% → **all twelve admitted**. Worst case at the new 8% stop is
  12 × 25% × 8% = **−24%**, not −2.9%. Wider stops on the same gross made
  Monday WORSE. This is P0.0 below and must land before Monday's open.
- hack5 is the design working as designed and the design being wrong: 5% of
  equity of premium per name × 5 names of **5-DTE OTM calls** on the same
  theme names as hack3/6 (QS $6 strike on a $5.9 stock; SMR $10 on $9.7). A
  −60% day on each is not a tail event for that structure; it is its median.
  The two "independent" risky books were the same bet in two instruments.
- hack1/2 lost 0.75% for a different reason: a **3% stop on NVDA six minutes
  after the open**, with the index down 0.1%. NVDA's opening 10-minute range
  is routinely >3%. That stop is a fee. (It also fired on Fed-speech noise
  the drift thesis never claimed to predict.)
- Learning loop: `scripts.counterfactual` has exited non-zero **17 times in a
  row on four of six loops** (hack1/2/3/6) because it sends share symbols
  (BBW, AG) to `client.option_quotes`. hack4/5 pass only because their untaken
  worlds happen to be options. `alpha/fills.py:mark_now` already has the
  correct routing (`symbol == underlying → stock_quote`); the counterfactual
  script never got it. Every refused-decision counterfactual since kickoff is
  unmarked.

What worked and must NOT be thrown away: the measured drift target (DKNG
+2.5% exit), the stop mechanics themselves (every stop filled; the BE
wash-trade refusal self-healed), genesis freeze, spend gate, the digest
running from Railway on schedule (08:02 UTC Sat, 141 names, 31 East articles,
4 providers live), discovery_autopsy receipt written.

## 2. VALIDATION OF THE GPT REVIEW (point by point)

| claim | verdict | note |
|---|---|---|
| six-account table | ✔ within $200 | equity read from `/v2/account` |
| "twelve names one bet" | ✔ but incomplete | gross 300% is the multiplier; see §1 |
| BE stop refused then replaced | ✔ | wash-trade vs own resting buy; healed next cycle |
| hack5 latch cannot neutralise existing calls | ✔ | but the calls were mis-specified at entry (DTE, moneyness), not just unhedged |
| counterfactual worker bug, "5 of 6" | ✔ on 4 of 6 | hack4/5 pass by luck of instrument mix |
| "Do not train the NN first" | ✔ agree | the ledger IS the dataset; stages 0–3 |
| "Do not reset accounts" | ✔ agree; Murat's call | see §8 |
| Murat's selection = analyst-upside × drawdown | ✔ and now RECONSTRUCTED from his own files | §3 |
| "premarket_digest cannot find the whole market" | ✔ | 141 names; the East pass is 4 GDELT queries + 31 articles |
| "Federalist" = Featherless | ✔ | `alpha/council/providers.py:77`; live; used for §7 |
| P0 order (counterfactual → stops → concentration → mesh) | ✘ reorder | a gross cap and the options DTE rule are cheaper and worth more on Monday than the concentration REPORT |

## 3. MURAT'S SELECTION METHOD — reconstructed from four files

Sources: `Downloads/stocks.pdf` (Sep 2025 dossier), `context for aegis/my
stocks old.pdf`, `stock research .pdf` and `stock (1).pdf` (portfolio at
07 Nov 2025 and 13 Jan 2026, "2025 +115%").

The colour code in the spreadsheets IS the rule. Green rows satisfy all of:

    (a) analyst 12-month consensus target / price  ≥ ~1.5   (most ≥ 2.0)
    (b) consensus rating ≥ ~4.1 / 5 (Buy–Strong Buy), typically 3–8 analysts
    (c) sector: biotech/medtech or "technology that the next decade needs"
        (chips, batteries, quantum, grid power, robotics, fintech platform)
    (d) a NAMED catalyst inside 12 months (Phase 3 readout, PDUFA, launch,
        pipeline restart, legal/regulatory decision)
    (e) price already DOWN from a recent level ("they were already down when
        I bought")

Red rows are the falsifier of the rule, not a mood: **target below price**
(SLDP 8.5 vs 7, BE 134 vs 110, MU 236 vs 210, QS 16 vs 10, MRNA rating 3).
Yellow is "rule passes but the driver is exogenous" (MSTR = BTC, APLT = cash
runway). Exits on record were rule-driven too: TVTX sold at 34.4 when upside
fell under 30%, ALMS sold at 10 when price reached half the target, SLDP
sold at 8.1 when the target dropped below price.

What happened next (Nov 2025 → Jan 2026) is the first out-of-sample test the
engine owes him: of the 14 greens with both prices, **9 rose, 5 fell**
(SOC 5→10.8, OLMA 8→28.8, RVMD 60→118, ALMS 4.5→21, SRRK 28→43.5 up;
TVTX 34→22.8, MSTR 250→163, AMSC 40→30.5, TGTX 33→27, GLXY 30→26 down).
**Rule-passing names carry both the +300% and the −35% tails**, which is why
the position sizing and the exit rule, not the screen, decide the P&L.

This becomes generator #4 ("analyst dislocation") and the Murat-lane in
`ACTIVE_ROADMAP` §4, with two amendments from his own data:
1. use **revision** (target and rating CHANGE over 30/90 days) alongside
   level — a static +50% target on a falling stock is the red SLDP row;
2. the drawdown condition must be split into *transitory* vs *thesis
   impaired* by whether the catalyst is still dated (AARD: clinical hold vs
   unblinded data in Q3 — both, and that is the bet).
Data: `scripts/analyst_panel.py` says the >50%-upside screen "cannot be
reproduced" from Alpaca; it needs a target source (Finnhub `price-target`,
FMP, or the panel's own recommendation-count proxy). Ship it with the source
named in the receipt.

## 4. MONDAY-SAFETY PATCHES — before 21:30 SGT Monday, in this order

**STATUS 2026-08-29 ~23:30 SGT (Opus): ALL SIX SHIPPED, DEPLOYED, VERIFIED.**
P0.4 (`alpha/drivers.py`: declared themes are the floor, measured correlation
may only MERGE two drivers, never split one; cap 40% of the profile's own gross
authority, so basket worst case at the 8% stop falls -8% -> -3.2%). P0.5
(`alpha/protect.py`: `covered >= want_qty` called SIDE FLIP, SHRINK and STACKED
"kept"; all three were live, all three now fail first). P0.2 remainder
(`alpha/crossbook.py` + `scripts/fleet --overlap`, which found BE held by hack3
in shares AND hack5 in calls RIGHT NOW). Plus, unplanned and larger than any of
them: **the counterfactual was publishing +$62,687,334 on a $99,250 book and
concluding "the gate is discarding edge -- loosen it or explain it"** -- the
options x100 multiplier applied to share legs, a floor with no ceiling, and a
pair priced from a hedge ratio nobody recorded. And Murat's rule conditions (a)
and (b) are now MEASURED, not asked: (a) 0/20 -> 14/20 resolvable, which puts
**BHVN (1.23) and SRRK (1.06) BELOW their own rule's upside bar** while MU
(1.61) passes. Terminal commits 11e31eb..c3b83cc; suite 43 -> 48 suites / 1,946
checks; deploys now carry `AAT_BUILD_COMMIT` and are verifiable from outside for
the first time. Full receipt: `docs/SESSION_2026-08-29_OPUS_BUILD.md` in the
terminal repo.

**STATUS 2026-08-29 21:30 SGT (Fable):** P0.0, P0.1, P0.2 (DTE + break-even + 15% premium; NOT the cross-account basket-overlap refusal), P0.3 (as a no-entry window 09:30–09:45, not a stop-width change) **SHIPPED and DEPLOYED** — terminal commit 9e47576 + the per-profile notional cap (basket 10%/name). P0.4, P0.5 **open** for Opus. Opus's Saturday build (§5 information layer) was reviewed, five required fixes applied, and committed in the same push; Optimus repaired (84108c4).

Murat's rule: fix and improve BEFORE the open, not never. These are small,
each is a refusal that Friday proved necessary, each ships with a test.

| # | change | file | acceptance |
|---|---|---|---|
| P0.0 | **gross notional cap per profile**: conservative 60%, aggressive 100%, maximum 150%, basket **100%**, convex n/a (premium cap) — enforced in `admission.admit` on post-trade Σ\|notional\| | `alpha/admission.py`, `alpha/engine/sizing.py` | test: 12 basket names at 25% → the 5th is refused with reason `GROSS`; basket worst case at 8% stop ≤ −8% |
| P0.1 | counterfactual quote routing: share legs → `stock_quote`, options → `option_quotes`, per-leg failure recorded as `missing`, never aborts the batch | `scripts/counterfactual.py` (reuse `fills.mark_now` split) | all six loops complete one cycle; receipt has marked/refused/missing counts |
| P0.2 | convex entry rules: DTE ≥ 2× horizon and ≥ 10 sessions; moneyness ≤ 1 expected move; premium-at-risk cap 15% aggregate; **theme names already held by a basket book are refused on the convex book** (one bet, one instrument) | `alpha/engine/sizing.py`, `alpha/refuted.py` | Friday's five calls all refused in replay, reason named |
| P0.3 | stop width = max(profile stop, 1.0× measured 10-min opening range) and **no stop evaluation in the first 15 minutes** for shares entered at the open; NVDA 09:36 stop refused in replay | `alpha/engine/equity.py`, `alpha/protect.py` | hack1/2 replay: no exit before 09:45 |
| P0.4 | concentration by DRIVER: a basket entry pass tags each name with its theme; Σ notional per theme ≤ 40% of the basket authority | `alpha/concentration.py` (exists), `alpha/fleet.py` | Friday's book prints 3 drivers (uranium, quantum, fuel-cell/solar) not 12 names |
| P0.5 | ACTIVE_ROADMAP P0.2 order/stop reconciliation tests | `alpha/protect.py` | synthetic: opposite resting order, partial fill, restart |

Then, and only then, redeploy: `python -m scripts.fleet --check-all` (fails
closed) → `python -m scripts.fleet --deploy all --up` → `railway logs` shows
`018d417+` and one clean `counterfactual --record` per loop.

## 5. BUILD ORDER Sat → Mon (absorbing ACTIVE_ROADMAP §2–§11)

**Saturday (after §4):**
- EventObservation schema + source registry (`ACTIVE_ROADMAP` §3.3), PIT
  `observed_at`/`effective_at`, provenance.
- Collectors, code only, no LLM: SEC EDGAR full-text + 8-K/Form 4/13D
  (`backend/services/insider_trading.py` and `copy_lab` sources exist — the
  Form 4 source has been STALE since 12 Aug and the 13D source returns 0;
  fix those first, they are already-built arteries), FDA calendar
  (Federal Register + sponsor IR pages), ClinicalTrials.gov completion
  dates, Alpaca news, GDELT (from Railway, where it does not 429).
- **Broad universe**: every US-listed name with options and dollar volume >
  $5M/day (≈2,500), not the 141. `scripts/window_universe` + `alpha/universe`
  already compute liquidity; widen, do not rewrite.

**Sat night / Sun (Asia hours):**
- Asia-first pass: HK/Shanghai/Tokyo/Seoul closes, exchange notices, CXMT /
  HBM / rare-earth / policy feeds → mapped to US exposures by an explicit
  edge table (v0 is a hand-written CSV of ~200 edges; the graph learns later).
- Generators 1 (event), 4 (analyst dislocation = Murat lane), 5 (undercoverage:
  independent-source count vs the name's own 90-day baseline), 7 (Asia lead).
  Each writes candidates to its OWN file; union happens in the prediction book.
- Catalyst calendar with `source_verified: bool` per row.

**Sunday:**
- **Sealed pre-open prediction book** (`state/predictions/<day>.json`, hashed
  at 09:15 ET): per candidate direction/magnitude/horizon/p_priced/falsifier/
  generator/which-book-acts. `scripts.thesis` and `premarket_digest` bets
  feed it; nothing trades that is not in it.
- Backtest factory v0 on CRSP 1993-2024 + IBES (already joined in the farm):
  **analyst-upside × drawdown cells** (Murat lane, conditional on sector and
  coverage count), event-type conditional replay for the printers in the
  window (PANW 2 Sep, AVGO 3 Sep, NFP 4 Sep — the last is a GAP, hold into
  it, add nothing), shares vs calls vs call-spreads at matched horizon.
  Rank on terminal wealth, report MDE, split the window.
- Discovery autopsy → research queue → next digest's `--symbols` (close the
  loop; today it writes a receipt nobody reads).

**Monday daytime SGT:**
- Stage 0/1 baselines on the event panel; conditional MoE prototype only if
  the panel passes the PIT/leakage check.
- Local-model lifecycle (§6). Cost report: calls by tier, $ per gradeable
  output.
- 20:30 SGT: freeze the Monday decision packet (`ACTIVE_ROADMAP` §15) and the
  prediction book. Nothing new touches an order after that.

**Shadow-only until it beats its baseline out of time:** every generator, the
mesh, the MoE, the NN. Paper authority stays with drift (measured), the
Murat lane at 3%/name under the gross cap, and the attended human thesis.

## 6. MODELS, COST, AND THE LAPTOP

- Measured now: **nothing resident**. 10.3 GB free of 32 GB RAM, GPU 428 MB
  of 8 GB, no llama/ollama/uvicorn process. The RAM Murat saw was the daily
  `analyst_panel` (05:30, fetch-bound, 690 names of bars) plus Chrome — not a
  model. Rule stands anyway: **load → batch → unload**, never a resident
  server; `llama\llama-stop.cmd` before gaming; the HF endpoints
  (`hf_glm`, `hf_deepseek_v4`) are remote and cost nothing idle.
- Tiering (unchanged from VISION §4.4/4.5, now with names): code fetches and
  extracts; local model / HF for embeddings, clustering, entity linking;
  DeepSeek for Chinese/Japanese/Korean reading and causal synthesis;
  Featherless / NVIDIA (kimi, minimax) as the council's independent voices;
  Fable red-teams. **Extend `alpha/spend.py` to refuse a call whose job a
  regex could do** (transcript number extraction).
- `providers.probe` order is deepseek → featherless → nvidia_kimi → hf_glm;
  the digest takes the first live one. To route a run to Featherless today,
  blank `AAT_DEEPSEEK_API_KEY` for that process (§7). Give it a `--provider`
  flag.

## 7. RUNS THIS SESSION (receipts)

- Railway hack6, Sat 08:02 UTC: `premarket_digest` — 141 names, 161 Alpaca
  headlines, 31 East articles; EAST→WEST read: Fed firm-rate stance, CXMT
  sues Pentagon, Cathie Wood trims AMD. Top bets MRVL +5%/3s (Google AI
  "monster number", score 2.45), BE +4% (NVDA power-bottleneck), DKNG +4%,
  RBRK +3%, CRM −3%, AVGO −3% (tariff), AG −3% (Warsh/mining). Council on
  MRVL/BE/DKNG/RBRK found **no cells** → nothing tradeable → correct refusal.
- Local, Sat ~13:40 SGT: condensed digest on **Featherless**, 48h window,
  Murat's names appended (`--symbols SLDP DKNG HUBS BHVN AMSC KYTX PRCH NTLA
  ABSI QUBT AARD SOC TSM MU MRVL AMD SRRK OLMA SLNO BEAM`). Output:
  `state/premarket/2026-08-29.json` (local). 156 names, 394 headlines, 67 East
  articles, Featherless only. Top: RBRK +10%/3s (score 4.0), AFRM, HPQ, ESTC,
  S, CRWD, NVDA (+5%, analysts to $400), AMD −5% (tariffs), MRVL −8% (already
  priced 0.9). **Not one of Murat's twenty names received a bet** — none had an
  Alpaca headline in 48h. That is the coverage gap in one line: the pipe only
  sees what Benzinga wrote about, so it re-discovers this week's earnings
  prints and never SLDP/KYTX/AARD. SHADOW; nothing trades on it.
- `discovery_autopsy` for 28 Aug ran on Railway; the local receipt
  `state/autopsy/discovery_2026-08-28.json` exists and is unread by any
  consumer (Sunday item).

## 8. FOR MURAT — decisions only you can make

1. **Fresh accounts?** Not needed for the code; the day is evidence. If you
   do reset: new keys into `.env` (never commit), `scripts.genesis --freeze`
   per role BEFORE any order, `fleet --check-all`, `fleet --deploy all --up`.
2. **Judged account:** hack6 is the flagship by mandate but is −9.3%; hack1
   is −0.75% and dull. Decide by Wednesday, say it in the write-up.
3. **PC on?** Not required for trading (Railway). Required for research runs,
   the local model and the 05:30 panel. Leave it on at night if you want the
   panel; otherwise the task just skips.
4. Merge the two docs branches after you read them: terminal PR #1
   (two amendments requested) and Aegis `docs/canonical-integration-20260828`
   (ACTIVE_ROADMAP; no PR open yet).

## 9. WHAT NOT TO DO (adds to ACTIVE_ROADMAP §14)

- Do not widen a stop without capping gross. Do not raise `aggregate` on a
  RISK fraction and read it as a notional limit.
- Do not let the convex book buy what the basket book holds.
- Do not read a Railway log line as a receipt; read the venue.
- Do not build the NN before the prediction book has 5 sealed days.

---

## 10. THE WEEK OF 31 AUG — NOVEL TESTS ON THE CORPUS AND THE SIX BOOKS (added Sat 29 Aug 22:40 SGT)

The corpus now holds 12 months of dated news and 6 months of dated future
events for the names we trade, and six paper books run every session. That is
enough to test STRATEGIES rather than stocks. Each test below names its
question, its data, its null and where the paper book comes in. None gets
order authority until it beats its null out of sample; every one writes a
receipt under `state/`.

| # | test | question | data / window | null | paper-book role |
|---|---|---|---|---|---|
| T1 | **Blind name-swapped LLM tournament** (`scripts/blind_tournament.py`) | once the name, ticker, products and prices are stripped, does 30 days of news carry direction for the next 21 sessions? | corpus 2025-09 → 2026-07, 20 names + SPY, Featherless | shuffled predictions ×200; canary identification rate must be < 5% | T7 runs the same protocol LIVE each pre-open at zero size |
| T2 | **Refusal-ledger NAV** | what would the book be worth if every refused decision had been taken, by refusal class? | the ledger's counterfactual marks (fixed 29 Aug: units, ceiling, pair fields) | the taken book | the six books ARE the treatment; the refused worlds are the control |
| T3 | **Sector-lead / laggard** (Murat's thesis) | when ≥3 names in one declared driver get positive attention+sentiment shocks in a week, does the driver's 20-day LAGGARD outperform over the next 21 sessions? | corpus features + `alpha/drivers.py` taxonomy + bars | same-driver leader; random name in the driver | hack6 shadow lane |
| T4 | **Coverage shock** (the normalisation thesis) | does attention_z > 2 pay MORE for names whose baseline is < 0.5 items/day than for names at > 5/day? | `corpus_features` panel, 2025-09 → 2026-07 | matched z, high baseline | — |
| T5 | **Catalyst approach / aftermath** | return in the 10 sessions before a dated catalyst vs 10 after, by sector and coverage | corpus `future` rows (earnings/PDUFA/readouts) observed PIT + bars | dates shifted ±30 days | informs whether the basket holds INTO a print |
| T6 | **Murat's rule cells** | PIT target/price ≥ 1.5 AND drawdown ≥ 20% AND rating ≥ 4.1 → 21/63-day return vs same-sector names failing one condition | broker-note extraction (Opus 26c1d4a), panel ratings, bars | one condition dropped at a time | the THESIS book (hack3) is this rule's live arm |
| T7 | **Live blind book** | prospectively: blinded pre-open predictions on the day's universe, sealed 09:15, graded at close, beside the NAMED digest | daily from Mon 31 Aug | the named digest's own hit rate — the difference is what the NAME adds | zero size; a prediction book only |
| T8 | **Two-instrument A/B** | the same decision as shares (hack2) vs defined-risk option (hack4) vs long premium (hack5): P&L per unit of max loss | `alpha/crossbook.py` pairs by decision, fills from the venue | shares | already running; formalise the paired grade |
| T9 | **Entry timing** | same signal filled at 09:45 / 10:30 / 15:50 (MOC): the overnight finding says MOC | shadow fills from minute bars | 09:45 | `runner.in_opening_range` is the first cut; T9 decides the rest |
| T10 | **Asia lead** | do FXI/KWEB/EWJ/EWY moves and HK-listed supplier prints predict the US open gap of mapped names? | ETF closes + a hand-written edge table v0 (~200 edges) | unmapped names | premarket digest East pass gets a NUMBER, not a paragraph |

**STATUS Sun 30 Aug (Opus): T2, T6, T3 RUN — AND ITEM 1'S RESULT IS WITHDRAWN.**
The features panel was 23 symbols while the corpus covered 156. Rebuilt over the
corpus universe (**152 symbols / 37,601 symbol-days**) and re-run through the
SAME harness over the SAME period: **0 of 29 features have a 95% CI excluding
zero, where 7 did on the 23.** `ev_insider_20d` +0.148 -> +0.023. It is the
universe, not the harness — re-running the same 23 from the wide build
reproduces +0.139. The 23 were Murat's own names over a window in which MU ran
+702.7%. Coverage is ruled out (coverage alone IC +0.0004; normalising moves the
ICs by <0.005). Receipt:
`aegis-alpha-terminal/docs/FINDING_2026-08-30_THE_EVENT_COUNTS_WERE_TWENTY_THREE_NAMES.md`.
**T7's sealed book therefore CLAIMS NOTHING** — `CLAIMING` is derived from the
CIs, so it turns itself on when a signal earns it (`scripts/prediction_book.py`,
hashed + append-only seals, 151 considered / 0 claims). **T6:** condition (b)
UNAVAILABLE (rating non-null on 135 of 37,601 — the PIT panel is 4 days old);
(a)x(e) every cell below its own MDE, and "already down" ALONE loses money
(0.92x), agreeing with the CRSP knife-basket adjudication. **T3:** 269 events,
six real drivers — the laggard beats the leader but LOSES to the middle of the
driver on mean, median and terminal wealth; no support for the laggard thesis.
T3 could not be ASKED before the panel widened. **T2:** 13 refusal classes in
three kinds (merit / book state / tournament), never pooled — a classifier bug
had put 473 forecast-level rows into AGGREGATE_RISK. Every scored class is
negative BUT the null is empty (the taken book's legs have expired), so it says
what the refused ideas are worth, not that refusing beat trading. **T1's
second-family control is BLOCKED**: hf_glm HTTP 402 (credits depleted),
nvidia_kimi HTTP 429; `--provider` now pins the family and refuses to fall back,
and the SPY control's blinding was deleting the macro story (`U.S`, `Iran`,
`Bessent`) until index instruments were exempted from derived aliases. Also:
four names in the 98-name trading universe are delisted/bankrupt and could never
have filled (GES, GMS, SNBR, TPIC — now 94). Terminal commits `46b595e..cabdb06`;
suite 51 -> **54 suites / 2,277 checks**. Full handoff:
`aegis-alpha-terminal/docs/SESSION_2026-08-30_OPUS_ROADMAP.md`.

**STATUS Sat 29 Aug 23:59 SGT:** items 1-3 SHIPPED (terminal commit "News becomes numbers…"): features panel + IC table (event counts carry; narrative does not), T1 blind tournament run = NO INFORMATION (receipt), sensors widened to 80,212 observations / 156 names / 149 with SEC filings. See `aegis-alpha-terminal/docs/FINDING_2026-08-29_BLINDED_NEWS_HAS_NO_DIRECTION_EVENT_COUNTS_DO.md`. T7 is now a CONTROL. Next: 4 → 5 → 6.

Build order for Opus (Sun → Wed), gates not dates:
1. `scripts/corpus_features.py` panel + IC table (news → numbers; this decides
   which features enter the sealed book) — **being built 29 Aug**.
2. T1 blind tournament, historical — **being built 29 Aug**; T7 is its live twin
   and reuses the code.
3. Wider sensors (EDGAR 8-K/4/13D, IR feeds, Alpaca news for the 160-name fleet
   universe) — **being built 29 Aug**; T4 needs the breadth.
4. T6 and T3 (one script, `scripts/rule_cells.py`), then T5.
5. T2 as a nightly report from the existing counterfactual marks.
6. T9/T10 after the book has a week of sealed predictions.

What "the NVIDIA tools" are (Murat asked twice): the NVIDIA Build key serves
**models** on an OpenAI-compatible endpoint — chat (kimi, minimax, gemma) and
**embedding/rerank** models. There is no NVIDIA scraper. Fetching is code
(Alpaca news, Finnhub, GDELT, SEC EDGAR, IR RSS); NVIDIA embeddings are used
for novelty and source-independence in the features panel. That is the
"embedding prototype" the 26 Aug roadmap allowed before 4 Sep.
