# ROADMAP 2026-09-08 — THE NIGHT ALPHA FACTORY ($0 overnight, and what the first hour found)

**Status:** TIER 1 amendment to `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md`. Written by
Fable 5.1 on the evening of 2026-09-08 (HK) for Murat and the Opus builder. The
night is RUNNING as this is written; the receipts are in
`backend/data/optimus/night_factory_2026-09-08/`.

**Murat's mandate (2026-09-08, verbatim in the parts that bind):** *"I'm not happy
with the backtest results ... We can't just claim everything we find out is noise
... run simulations throughout the whole night, back to back, and continuously
learn, make up correlations ... supervised learning with NN should be necessary
... I don't want Claude to use any credits."* And: *"check the alpaca paper
accounts make sure they are not also left unattended and empty."*

---

## 0. SCOREBOARD (first paragraph, per the 2026-08-24 rule)

| | |
|---|---|
| **RESULT IMPROVEMENT** | **NONE on any book yet.** One finding moved: the earnings-reaction **long** leg does not survive a faithful event-clocked book at 25 bps in any era after 2015; the **bottom** reaction decile keeps falling in all three eras (t −4.7). That changes what hack2 may become (§3). |
| Paper accounts | Were **EMPTY at the open** for a fifth day. Cause found and fixed for hack3 (a sentinel judged a direction brain on a width it never claimed; terminal `329adb5`, redeployed, filled 13:54Z). hack6 filled on its 14:01Z pass. At 14:04Z: hack3 7 positions, hack6 11, hack5 1; hack1/hack2/hack4 empty by design or by a gate that is Murat's flip. |
| LLM spend | **$0.00** Claude, **$0.00** DeepSeek (balance $9.11, unchanged). Local Qwen2.5-7B on the GPU at ~93% utilisation. |
| Running now | CPU queue PID 166169 (D1 done → D2 done → **G1 evolving until ~21:00Z**); GPU job PID 166212 (**C1 curriculum until ~21:00Z**). STOP file: `night_factory_2026-09-08/STOP`. |
| Best historical net line | unchanged (`ensemble_ew|k=100|ew|hold=200|10bps` 62.87 vs 13.18, β 1.195, NOISE family-corrected). G1's DEV archive prints larger numbers **on the development window only**; they mean nothing until G2 reads the holdout once (§2.4). |

---

## 1. TWO RULERS, TWO LEADERBOARDS, AND THE END OF "NOISE" AS A DELETE KEY

Adopted tonight, in code (`scripts/night_factory.py::append_leaderboard`, `_status`):

| list | ruler | who lands there |
|---|---|---|
| **RESEARCH_PROVEN** | the alpha ruler: Holm over the family, DSR/PBO, three eras, placebo, MDE | only a pre-registered lane (`pre-register-trial`) |
| **PRODUCT_PROMISING** | the product ruler: **β first**, terminal wealth net of costs at a drawdown budget, on the DEVELOPMENT window | every night job |

A row that fails the first ruler is **never deleted**. It moves to the second with a
typed status, and the status is the finding:

`PRODUCT_PROMISING` (β-matched positive, every era same sign, placebo does not
reproduce it) · `CONDITIONAL` (positive, not in every era or not powered) ·
`BETA_ONLY` (beats the market raw, not β-matched) · `CONSTRUCTION_SENSITIVE`
(the event-level effect exists, the book does not carry it — D1 tonight) ·
`REGIME_SPECIFIC` · `FAILED_VARIANT` (this implementation) · `MECHANISM_REJECTED`
(reserved for broad evidence, as before).

What this changes: the search is allowed to be aggressive on **1999-2015**; the
**2016-2024 window is read once, by a named job, in the morning**, and the reading
is the verdict. "Noise" is a statement about a claim, not an instruction to stop
looking. What it does NOT change: PIT, costs, frozen versions, no LLM authority
over capital, no backfilled forward evidence.

---

## 2. THE NIGHT'S MACHINE (what runs, where, on what, at $0)

```
 GPU (llama-server, Qwen2.5-7B Q4, port 8080)      CPU (20 cores, 32 GB)
 ───────────────────────────────────────────       ──────────────────────────────────────
 C1  counterfactual news curriculum                D1  faithful event-clocked reaction book   (done, 41 s)
     scripts/night_c_counterfactual_news.py        D2  ten mutations on DEV, holdout marked    (done, 39 s)
     ~500-800 docs/hr, resumable by uid            G1  evolutionary construction search, DEV   (running, 7 h)
     rows: C1_counterfactual_news.jsonl            G2  READ THE HOLDOUT ONCE                   (morning, Opus)
                                                   scripts/night_factory.py → night_factory_jobs.py
```

### 2.1 D1 — the faithful earnings-reaction book (R4 §12 item 1, the test it owed)

`D1_reaction_book_run01.json`. Enter at the close of session +1 after each IBES
announcement (PIT-safe for after-the-bell reporters), rank the two-session
reaction against the trailing **63 sessions of events** (pool ≥ 200, everything
known at the close it is used), $3m/day floor, calendar-time equal weight across
open positions, **25 bps a side on entry and exit**, β printed first, monthly date
blocks, three eras, the +40-session placebo through the **same** book. 338,962
announcements, 18,468 top-decile positions, ~59 open at a time.

| cell (1999-2024) | β | β-matched %/yr | t | TW net | TW **gross** | market | max DD |
|---|---|---|---|---|---|---|---|
| top decile, hold 21 | 1.40 | **−4.14** | −1.09 | 3.76 | **26.06** | 8.26 | −55% |
| top decile, hold 42 | 1.46 | −4.36 | −1.78 | 4.47 | 13.01 | 8.26 | −63% |
| top decile, hold 5 | 1.11 | −17.0 | −2.52 | 0.03 | 17.74 | 8.26 | −97% |
| **bottom decile, hold 21** | 1.63 | **−20.0** | **−4.70** | **0.07** | 0.48 | 8.26 | −95% |
| placebo top decile, hold 21 | 1.66 | −14.9 | −2.67 | 0.16 | 1.14 | 8.30 | −96% |

Eras of the top decile at 21 (β-matched t): **+1.17 / +0.11 / −2.88**; the bottom
decile: **−2.93 / −2.97 / −2.48**. Family (8 long cells) Holm min p 0.095.

**Reading, in order of consequence:**

1. **The construction tax is the whole story for the long leg.** Gross 26× against
   the market's 8× becomes 3.8× net: a 21-session round trip at 50 bps is a
   ~7.4 %/yr cost line, and the long leg's β-matched edge is ~+3 %/yr gross. R4's
   breakeven of 39-45 bps a side was computed on the top-minus-**bottom** spread;
   the long leg alone breaks even near 20 bps. **At the repo's 25 bps grid the
   reaction long book is not a product.** D4 (§5) prices it at 10 bps on a liquid
   universe, which is the only way it can come back.
2. **The information is in the losers.** The bottom reaction decile continues DOWN
   in every era, t −4.7, β-matched −20 %/yr, gross terminal wealth 0.48. That is
   rule 4 of the mission (study losers as hard as winners) paying out: it is an
   **exit/avoid rule** for the long books tonight (a held name that prints and
   lands in the bottom reaction decile is THESIS_INVALIDATED) and a candidate
   **put/short shadow book** for hack5's options mandate — not a long book.
3. **R4's +1.80 % spread carried a rank look-ahead.** Its deciles were formed
   within the calendar month, so an event on the 3rd was ranked against events
   on the 28th. The PIT trailing-window rank on the same floored tape gives a
   top-minus-bottom event-level spread of **+0.76 %** (−0.04 % vs −0.79 %). The
   effect is real, half the size, and almost all of it is the bottom decile.
4. **2016-2024 is negative for every long variant** (D2 below). The placebo still
   flips the sign relative to the event book (−14.9 vs −4.1 %/yr), so the event
   still does the work; it just does not pay a long-only book after costs.

### 2.2 D2 — ten mutations on DEV (1999-2015), holdout printed and marked

`D2_reaction_mutations_run01.json`. DEV t, then the marked 2016-2024 column that
chose nothing:

| variant (top decile unless said) | DEV β | DEV β-matched %/yr | DEV t | Holm | 2016-24 β-matched %/yr | 2016-24 t |
|---|---|---|---|---|---|---|
| z-scored reaction (÷ trailing 60-d σ) | 1.05 | +6.0 | **2.13** | 0.33 | −15.7 | −4.35 |
| × volume surge ≥ 2× | 1.34 | +9.0 | 1.91 | 0.50 | −18.5 | −2.96 |
| × small half | 1.19 | +18.1 | 1.45 | 1.0 | −26.5 | −2.42 |
| base | 1.42 | +3.5 | 0.83 | 1.0 | −18.9 | −2.91 |
| top quintile | 1.30 | −0.0 | −0.01 | 1.0 | −17.5 | −3.70 |

**Every variant is negative in the holdout.** No mutation of the long leg is a
book at 25 bps. The z-scored rank is the right *representation* (it is what the
NN lane should ingest, §5 N1) and the wrong *product*.

### 2.3 G1 — evolutionary construction-and-selection search, DEV only (running)

`scripts/night_factory_jobs.py::G1_evolve`. Genome = weights in {−1, −½, 0, ½, 1}
over 14 z-scored features of the long panel × k ∈ {20..300} × {ew, rank, vw} ×
hold band {none, 2k, 4k, 8k} × floor {none, $3m, $10m}. Fitness = the product
ruler: `log(terminal wealth net of 25 bps) − 2·max(0, maxDD − 35%)·years/10`,
β and β-matched t on every row. Population 32, elitism 4, four random genomes
per generation, ~0.5 s per evaluation, **every evaluation appended to
`G1_evaluations.jsonl`** (the evidence memory; a restart resumes from it).

At 14:03Z, generation 15, 387 genomes: best DEV fitness 4.57 — terminal wealth
**112.6 vs the market's 2.71 over 1999-2015**, β 0.89, β-matched t 5.05, max DD
−39.5 %. **This number is the exam being learned, and it is printed so that the
morning can measure exactly how much.** G2 reads 2016-2024 once for the top-10 and
the Pareto set, beside 200 random genomes' holdout as the null bar; a genome whose
holdout t sits below the random p95 learned the exam. That reading is the verdict,
and it lands on the leaderboard with a typed status — not a deletion.

### 2.4 C1 — the counterfactual news curriculum (running, GPU)

`scripts/night_c_counterfactual_news.py`. From the terminal corpus (1,021,105
docs; 615,794 with body+symbols; **69,520 in 2020-2024, the years CRSP prices
exist** — those first), each real headline is anonymised (companies, people,
products → placeholders, tickers stripped before the model sees them) and the
local model writes three one-change counterfactuals — sign flip, ×3 escalation,
actor/timing — each with its implied direction, plus event type / direction /
magnitude for the original. 3/3 on the plumbing test, 4.5-11 s per document.

**The line it must never cross, and does not:** it writes NO return, NO price, NO
outcome. It is a curriculum for the text arm (causal ordering, sentiment
sensitivity, memorisation-proof by anonymisation). The supervised money labels are
always the market's own returns on the REAL headline, joined through E0. We never
tell a network "this invented story caused +8 %".

---

## 3. WHAT THIS CORRECTS IN MY OWN 2026-09-08 DECISIONS (§4, hack2)

I wrote that hack2 becomes the EARNINGS-REACTION book *after* the faithful
backtest. The faithful backtest ran, and the answer is **no long book**: at 25 bps
the long leg is `CONSTRUCTION_SENSITIVE` and post-2015 negative. So:

- **hack2 does not get a long reaction v2 contract.** The v2 contract in
  DECISIONS §4 is withdrawn before it was frozen; nothing was armed.
- The finding goes where it pays: (a) an **exit clause** for hack3/hack6 — a held
  name whose print lands in the bottom reaction decile exits (typed
  `THESIS_INVALIDATED:reaction_bottom_decile`); (b) a **zero-capital shadow put
  book** on liquid bottom-decile names for hack5's options mandate; (c) the
  z-scored reaction and "sessions since print" enter the NN lane as features.
- The "one constantly-active book to test and learn" is now the **AVOID/EXIT
  counterfactual on the live books**, graded nightly (did the rule's exits beat
  held-to-horizon?), which is active every session and costs nothing to learn from.

---

## 4. GPT'S TWENTY POINTS — adopted, adopted with a change, or already here

| # | point | verdict | where |
|---|---|---|---|
| 1 | two leaderboards, typed statuses | **ADOPTED** tonight | §1, `night_factory.py` |
| 2 | NN mandatory to TRAIN, not to believe; LightGBM stays | **ADOPTED** | lane N1 (§5); `learner_v2` exists (CPU torch, no CUDA on this box) |
| 3 | E0 first; FNSPID as a research benchmark | **ADOPTED**, licence check first | lane E0; C1's 2020-24 priority is E0's material |
| 4 | run the reaction faithfully, then mutate | **DONE** — result §2.1-2.2 | D1/D2 |
| 5 | made-up news as curriculum, never as return labels | **ADOPTED, in code** | C1 |
| 6 | multi-task multi-horizon NN with residual targets | **exists** (`learner_v2`: 1/3/6/12 m heads, `resid_vw_*`); extend features | N1 |
| 7 | route BEFORE truncation | ADOPTED as a G1 v2 gene | §5 G3 |
| 8-9 | evolutionary factor search, LLM only on stagnation | **ADOPTED** (G1); LLM-on-stagnation is a G3 item, local Qwen only | G1/G3 |
| 10 | manufacture X(t−lag)→Y(t+h) hypotheses across sources | ADOPTED as a G3 gene family once E0/I2 features land | G3 |
| 11 | Form 4 as features, not a rule | **ADOPTED** | I2 |
| 12 | unsupervised states as features | ADOPTED (U's state probabilities already on disk) | N1 |
| 13 | residual targets | exists | N1 |
| 14-15 | joint construction, learned exit | G1 is construction-joint already; exit policy = G3 gene + the D1 avoid rule | G3, §3 |
| 16 | Pareto frontier | **ADOPTED** (`pareto_dev` in G1) | G1 |
| 17 | walk-forward all night | learner is per-year walk-forward already; G1 is DEV-only by design | — |
| 18 | RD-Agent-style scheduler | ADOPTED as a budget rule on the queue (§5 T1) | night_factory |
| 19-20 | don't copy 1,300 % projects; don't let honesty paralyse | agreed; the ruler here is harder and stays | §1 |

Two GPT claims corrected by tonight's receipts: "the earnings-reaction spread is
1.80 %" is **+0.76 % PIT** (§2.1 item 3), and "hack6's old 3 % stop" is already
replaced in the live 63/21/12 % seal (`63010b2c…`, sealed 12:49Z today).

---

## 5. THE LANES (Opus session, agents on `model: "opus"`, $0 LLM)

Gates, not dates. Every lane writes a receipt before prose and appends to the
night leaderboard with a typed status.

| lane | what | gate / input | output |
|---|---|---|---|
| **M1 G2 read-once** | `python -m scripts.night_factory_jobs G2_holdout_once` after G1 ends (~21:00Z) | G1 receipt exists | `G2_holdout_once_run01.json`; verdict per genome vs random-genome null; leaderboard rows |
| **M2 D3 losers** | bottom reaction decile by size tercile, liquidity, VW; borrow-cost-aware short and a put-proxy; the AVOID/EXIT counterfactual on hack3/hack6's sealed names since 08-31 | D1 receipt | `D3_bottom_decile.json`; an exit-clause draft for the contract |
| **M3 D4 cost floor** | the long reaction leg at 10 bps and at 5 bps on names above $50m/day; breakeven curve | D1 | `D4_cost_curve.json` — the number that decides whether any long reaction book exists |
| **E0 joined panel** | ticker→permno by date through CRSP stocknames; 2020-2024 news with bodies (69,520) joined to daily returns; 2025-26 via Alpaca daily bars | corpus + WRDS on disk | `E0_joined_panel.parquet` + coverage receipt (all four readings named) |
| **N1 NN, extended features** | add to the long table: z-scored reaction decile, sessions since print, bottom-decile flag (from D1's event frame), U state probabilities, I2 Form 4 aggregates; retrain `learner_v2` (CPU) with residual targets; grade under BOTH rulers | E0 not required; event frame from D1 | `learner_v3_<date>.json`; paired vs v2 |
| **I2 Form 4 features** | per name-month: net insider $ / cap, n insiders, cluster flag, role, post-print timing | 11.5M rows on disk | `features_insider.parquet` + receipt |
| **G3 evolve v2** | genes for event features, the avoid rule, exit policy (hold-band by realised move), routing before truncation; PBO-CSCV across DEV folds (`reference/Vibe-Trading/.../multipletesting.py`); local Qwen proposes 5 structurally new genomes only after 30 stagnant generations | G1 archive | `G3_*` receipts; still DEV-only |
| **T1 scheduler** | night queue gets a budget rule: minutes per family ∝ recent improvement + novelty (RD-Agent's bandit, without the API) | — | `night_factory.py` change + test |
| **R pilot** | era replay 2 years with local Qwen on C1's anonymisation recipe; measures the memory canary first (AMNESIA-1 protocol) | C1 rows | `R_pilot.json` |
| **X carry-over** | taskkill hook (settings still allow `Bash(taskkill:*)`), 4th Sunday suite | — | — |

**Attended, Murat only:** hack4 v2 contract (no `requires_catalyst`) and its flip;
whether the bottom-decile exit clause is frozen into hack3/hack6's next seal;
DeepSeek top-up is NOT needed for any lane above.

---

## 6. RULES OF THE NIGHT (enforced by the scripts, restated for agents)

1. **$0.** No Anthropic, no OpenAI, no DeepSeek. `local_gguf` only; NIM as the
   second opinion. `free_inference` refuses rather than falls back.
2. **The holdout is read once, by G2, in the morning.** No job evaluates
   `month > 2015-12` on a searched object. D2 printed it beside unselected cells
   and said so on every row.
3. **Receipts before prose; a traceback is a receipt.** Every job writes its JSON
   before the next starts; `LEADERBOARD.md` gets one typed row per job.
4. **Kill by PID only** (166169 queue, 166212 C1; llama-server by
   `llama-stop.cmd`). The STOP file ends the night between jobs and inside G1/C1.
5. **Nothing is ordered, sealed, pushed or deployed by a night job.** The one
   deployment tonight (hack3, `329adb5`) was Fable's, on Murat's explicit
   instruction, with a receipt in the terminal repo
   (`state/deploy_receipts/2026-09-08_hack3_sentinel_fix.json`).
6. **A number without a receipt is prose** — including the 112× in §2.3.

---

## 7. THE FLEET, AS LEFT AT 14:04Z

| book | positions | why |
|---|---|---|
| hack3 | 7 of 10 (4 orders working) | sentinel fix deployed 13:52Z; first pass filled |
| hack6 | 11 of 15 | opening-range gate refused 15/15 at 13:30:40Z (40 s after the bell — by design); the 14:01Z pass filled, refusals none |
| hack5 | 1 (SMR call) | options book; evidence/risk/cash refusals on the rest |
| hack1 | 0 | manage-only survival layer, by declaration |
| hack2 | 0 | post_event_drift evidence gate (13 refusals); no contract of its own yet (§3) |
| hack4 | 0 | sealed book has 0 names — `requires_catalyst`; v2 contract is Murat's flip |

Worst case printed for tonight's live books: hack3 83 % gross at a 12 % stop =
−9.96 % (−$9.0k); hack6 90 % gross at a 10 % stop = −9.0 % (−$8.2k). Paper.
