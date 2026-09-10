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

---

## 8. THE SECOND QUEUE (added 22:55 local, while G1 was still running) — AND THE CORRECTION IT FORCED

`$0. No LLM. Two new jobs: D3 (done) and N1 (training until ~06:00 local).`

### 8.1 D1 graded every cell against ZERO while its own placebo lost 14.9%/yr

The single most informative number in `D1_reaction_book_run01.json` was printed
and then not used: **`PLACEBO_top_decile|hold=21` = −14.868%/yr beta-matched,
t −2.672.** The placebo is the *same names, the same construction, the same
25 bps, announcement dates shifted +40 sessions* — it carries **zero** event
information. That −14.9%/yr is therefore the **construction's own drag**, and it
is the baseline every D1 cell owed a comparison to.

`_verdict()` used the placebo only as a **veto** (`pt < 1.0` blocks a green
stamp) and never as a **baseline to subtract**. So the machine structurally
could not report "positive relative to control" — the same shape as
[[reference_gate_that_cannot_go_green]].

Read against the control instead of against zero, D1's own numbers reorder:

| cell | vs ZERO | vs its own control | reading |
|---|---|---|---|
| `top_decile\|hold=21` | −4.138%/yr | **+10.7pp/yr** | the best cell in the family |
| `bottom_decile\|hold=21` | −20.013%/yr | **−5.1pp/yr** | mostly the construction |

### 8.2 D3 — every leg differenced against its own matched control

`night_factory_jobs.D3_matched_control_grid`, receipt
`D3_matched_control_grid_run01.json`, corrected reading in
`D3_verdict_amendment.json`. Primary family fixed **before** the run: the
long-short at four holds. Everything else is tagged DIAGNOSTIC / ZERO_COST /
CONSTRUCTION_BASELINE and carries no Holm.

**Finding 1 — the bottom-decile EXIT clause is NOT earned. Do not seal it.**

The control that had never been computed anywhere:
`placebo_bottom_decile|hold=21` = **−16.315%/yr, t −3.753**, through the
identical book on dateless events. The announcement bottom decile was
−20.013%/yr. The incremental:

| hold | bottom minus its own control | t |
|---|---|---|
| 5 | −2.384%/yr | −0.231 |
| 10 | −2.572%/yr | −0.345 |
| **21** | **−4.006%/yr** | **−0.789** (p 0.43) |
| 42 | −3.783%/yr | −1.387 |

Era signs flip (−19.1 / +0.4 / +6.9). No hold reaches |t| 1.4. **The t −4.7 that
the exit rule rested on was the construction**, which a placebo reproduces at
−16.3%/yr. `hack3`/`hack6`'s next seal should NOT carry the bottom-decile exit
clause on this evidence.

**Finding 2 — the self-financing long-short is real, clean, and OLD.**

`LS_announcement|hold=21` (top decile long, bottom decile short, 25 bps on both
legs, calendar time): **β −0.2192, beta-matched +15.919%/yr, t 3.864**,
TW 20.17, DD −54.7%, vol 21.1%, 310 monthly blocks.

- **Holm max p 0.032** across all four holds — every hold survives the family.
- **placebo long-short t 0.02** — the control is dead flat. This is the number
  that makes it a finding rather than a construction artefact.
- Powered: 161 blocks needed for the observed effect, 310 on hand.

And the caveat that governs it:

| era | beta-matched | t |
|---|---|---|
| 1999-2007 | +28.705%/yr | 3.969 |
| 2008-2015 | +17.335%/yr | 2.370 |
| **2016-2024** | **+2.112%/yr** | **0.367** |

All three eras are the same *sign*, which is what the verdict rule counted — so
it stamped `PRODUCT_PROMISING`. That stamp is **wrong in substance**: the effect
decays monotonically to zero in exactly the window we would trade. The guard now
returns **`ERA_DECAYED`** for this shape (`_verdict_d3`), and the receipt is left
byte-for-byte as written with the corrected reading in the amendment file beside
it. *Same sign in every era is not the same as alive today.*

**Not modelled, and material to any long-short claim:** stock borrow / locate
cost on the short leg, short availability for a decile of small falling names,
and a −54.7% drawdown at 21% vol. This is not a low-risk spread.

**Finding 3 — the construction carries the drag, and that is why D1 inverted.**

An equal-weight book of **every floored announcer, no selection at all**, hold
21: **−7.700%/yr beta-matched, t −4.063**, β 1.211. Zero-cost diagnostics on the
same window: `ann_top` +3.586%/yr (vs −4.138%/yr at 25 bps — the cost line is
~7.7pp/yr), `ann_bottom` −12.035%/yr, `plc_top` −7.363%/yr, `plc_bottom`
−8.887%/yr.

### 8.3 N1 — the learner (running, PID 140516, time box 7 h)

`night_factory_jobs.N1_train_reaction_learner`. Trains on the **event level**,
which is the point: D3 shows the calendar construction carries a large drag that
signal and placebo share, so a model trained on *book* returns would spend its
capacity learning the drag. The label is the event's own forward
market-adjusted return (gross, truncated exactly the way `calendar_book`
truncates a position); the construction is then applied to the model's output,
where it belongs.

- purged walk-forward by year, **embargo = the horizon** (an event still open
  when the test year opens is dropped from training, not trusted);
- LightGBM, 400 trees, NaN native (no `fillna`);
- the identical pipeline is trained and traded on the **placebo** events, and
  `learner_minus_control|long_short` subtracts whatever the pipeline
  manufactures from no information;
- grid: 4 holds × 3 feature sets (`all` / `no_reaction` / `reaction_only`) ×
  3 seeds, resumable via `N1_configs.jsonl`;
- **primary fixed before the run**: `H21|all|s0`. The holdout is printed for
  every config and chooses nothing.

The `no_reaction` arm is the ablation that matters: if it scores as well, the
learner was trading size/momentum/volatility and the earnings event was
decoration.

### 8.4 What the morning reads, in order

1. `D3_verdict_amendment.json` — the exit-rule flip (**do not seal it**).
2. `N1_train_reaction_learner_run01.json` — primary `H21|all|s0`, and its
   `learner_minus_control` cell before any raw t.
3. `G2_holdout_once` — unchanged, still reads the sealed window once.

### 8.5 A trap closed on the way

N1's resume cache is keyed `H21|all|s0`, which says nothing about which tape
produced it — so a `--smoke` run would have made the real night skip all 36
configs as "already done". Smoke now writes `N1_configs_smoke.jsonl`. Same
family as the mtime-dated gate: **a cache key must name everything that changes
the answer.**

### 8.6 D4 — the long-short is real, and it lives below the tradability floor

`night_factory_jobs.D4_ls_robustness_and_decay`, receipt
`D4_ls_robustness_and_decay_run01.json`. 48 construction corners
(cost 0/10/25/50 bps × decile width 5/10/20% × floor $0/1m/3m/10m), each with
its **placebo twin**, plus a two-sample Newey-West test on the halves.

**Verdict: `CONTROL_ALSO_FIRES` + `DECAY IS MEASURABLE`.**

All 48 corners keep the long-short at |t|>2 — but so do **8 placebo corners**
(chance ≈ 2.4), and every one of those 8 is at **floor = $0**:

| floor | pooled | late (2016-2024) | decay t | placebo t |
|---|---|---|---|---|
| $0 | +24.377%/yr t 6.525 | **+22.067%/yr** | 0.431 | **−2.918** |
| $1m | +16.829%/yr t 4.685 | +6.309%/yr | 2.169 | −0.159 |
| $3m (D3's corner) | +15.919%/yr t 3.864 | +2.112%/yr | 2.740 | 0.020 |
| $10m | +15.576%/yr t 3.237 | **−0.130%/yr** | 2.510 | 0.129 |

Two things follow, and they point the same way:

1. **With no liquidity floor the construction manufactures a spread from
   dateless events** (placebo t −2.9 at every cost level). The floor is not a
   detail; it is what separates the event from the microstructure.
2. **The part still alive after 2015 lives below the floor.** Late-window
   corners positive: **12/12 at $0, 8/12 at $3m, 0/12 at $10m.** Median late
   return falls +22.06 → +6.30 → +1.85 → −1.10 %/yr as the floor rises.

The decay itself is measurable, not just noisier: early +23.301%/yr (202
months) vs late +2.112%/yr (108 months), **difference 21.190%/yr, t 2.740,
p 0.0061.** By-year at D3's corner, 2016-2024 reads
`+13 +14 −1 −5 −12 −17 +36 −13 +3` — no persistent edge, and 2022 alone (+36)
carries the era's positive sign.

**Conclusion for the morning:** the earnings-reaction long-short is a real,
Holm-clean, placebo-flat effect **in 1999-2015 and in names we cannot trade**.
It is not a book to seal today. Combined with §8.2 Finding 1, the whole hack2
reaction lane closes as `RETIRED_FROM_CURRENT_SEARCH` on the long-only *and*
long-short forms — and **neither** the exit clause nor a shadow-put book is
earned. What survives is a measurement, not a position.

---

## 9. THE NIGHT AS CLOSED, 2026-09-09 08:30 LOCAL

Every job finished and exited; no orphans. **$0 of paid LLM** — every receipt
carries `llm_spend_usd: 0.0`, and C1 ran on the local Qwen.

| job | result |
|---|---|
| D1 / D2 | as before — **D1's reading superseded by D3** (§8.2) |
| D3 | exit rule NOT earned; long-short +15.919%/yr t 3.864, placebo t 0.02 |
| D4 | `CONTROL_ALSO_FIRES` + `DECAY IS MEASURABLE` — the survivor is below the floor (§8.6) |
| N1 | 156 configs; primary `FAILED_VARIANT`; one live candidate at H5 (§9.1) |
| G1 | 40,680 genomes on DEV, best fitness 6.21341 (TW 547.94 vs mkt 2.71) |
| G2 | the sealed window, read properly on the second attempt (§9.2) |
| C1 | 4,669 of 4,839 counterfactual docs, ~690 docs/hr, local GPU, $0 |

### 9.1 N1 — the pre-specified primary failed; H5 is the one live candidate

156 configurations (4 holds × 3 feature sets × 13 seeds). The primary was fixed
before the grid ran and it **failed**: `H21|all|s0`, IC +0.047, long-short
+3.603%/yr **t 0.604**, DD −86.5%. Across 13 seeds `H21|all` never reaches
t 2 (max 1.84) — that is a stable negative, not a noisy one.

But `H5|all` is significant on every seed, and it survives the checks H21 does not:

| cell (`H5\|all\|s0`) | β | beta-matched | t |
|---|---|---|---|
| learner long-short | −0.276 | **+44.462%/yr** | **4.306** |
| placebo-trained control | 0.020 | −3.099%/yr | −0.450 |
| **learner minus control** | −0.297 | **+32.214%/yr** | **2.923** |
| holdout 2016-2024 (read, chose nothing) | 0.196 | +28.345%/yr | 1.419 |

Across 13 seeds: median +35.99%/yr, t 3.27, **control fires in 0/13**. Eras
+29.2 / +71.7 / +35.2 %/yr — **no decay**, unlike the reaction long-short.

**What it is not:** a claim. It was found by searching 156 configurations *after*
the pre-specified primary failed (39 of 156 clear t 2, uncorrected). It carries a
**−78% drawdown at 46% annualised vol**, on a 5-session hold whose turnover is
brutal, and the short leg's **borrow cost is still not modelled**. It is a
candidate for a pre-registered lane (`pre-register-trial`), not a book.

### 9.2 G2 — and the gate that could not go green

**The first G2 run read nothing.** `evaluate_genome` carried a hard-coded
`months < 150` refusal written for the 202-month DEV window. The sealed window is
**107 months**, so every one of the 235 evaluations — 35 archive **and** all 200
random genomes — was refused before a single statistic was computed, while the
receipt's headline read *"35 archive genomes read on the holdout once against 0
random genomes"* and `READ_ONCE: true`. The floor now travels with the window
(`min_months`, default 150, G2 passes 96), and an empty null bar **refuses
loudly** instead of printing a success-shaped headline.

Because nothing was computed, no holdout information reached any selection
decision, and run 2 is the genuine first read.

**The read (run 2), 30 unique genomes (5 appear in both the top-10 and the
Pareto set) against 200 random genomes:**

| | archive | random null | market |
|---|---|---|---|
| terminal wealth | median **9.69** (max 22.13) | median 2.51 | **4.86** |
| CAGR | 29.01% | — | 19.41% |
| β on the sealed window | median **1.130** (max 1.45) | — | 1.0 |
| max drawdown | median **−42.2%** | — | — |
| beta-matched excess | median **+7.19%/yr** | p50 t −1.986, p95 t **+0.072** | — |
| beta-matched t | median **0.861** | — | — |

- **35/35 archive rows sit above the random p95** and all are positive
  beta-matched on a window they never saw. Directionally, the search generalised.
- **Only 1 of 35 clears t 2** (≈1.75 expected at 5%), so **no alpha claim**.
- The rows are **not independent**: 30 unique genomes sharing ancestry, so the
  35/35 sign count is worth far less than it looks.
- β 1.13 median and **DD −42.2% against a declared `DD_BUDGET` of 0.35** — the
  archive **overshoots its own drawdown budget** on the sealed window.

**Verdict:** G1's DEV headline (TW 548× vs market 2.71×) becomes **9.69× vs
4.86×** on the sealed window, at β 1.13 and −42% drawdown. That is levered beta
that beat its budget, not a demonstrated edge — exactly what §2.4 said the DEV
numbers would be worth until this read happened. `DEV ARCHIVE` closes as
**BETA_ONLY**.

### 9.3 What is actually open tomorrow

1. **Do not** put the bottom-decile exit clause in hack3/hack6's seal (§8.2).
2. **Do not** seal the reaction long-short in any form (§8.6).
3. **Pre-register `H5|all`** if it is to be pursued — matched control, borrow
   cost, and a drawdown budget it can meet, before any capital question.
4. hack4's v2 contract remains Murat's flip, untouched by the night.

---

## 10. MURAT'S 2026-09-09 MANDATE — randomised windows, six armed books, the app, the day run

Written by Fable 5.1 on 2026-09-09 (10:00-12:00 HK) after reading §§8-9. The
review of the night's method is `REVIEW_2026-09-09_FABLE51_ON_THE_NIGHT_AND_THE_BACKTEST_METHOD.md`;
the builder prompt for the whole-day run is `NIGHT_2026-09-09_OPUS_DAY_RUN_PROMPT.md`.

**Murat (verbatim in the parts that bind):** *"randomize backtest a bit ... four-year
interval, five-year interval, six-month interval ... from 2000 to 2025 ... really
randomized times ... see when it beats the S&P 500, what it was focusing on ...
differentiate if it was noise or not"* · *"use the LLM to convert the news of that
time ... validate it in monthly intervals or six-monthly intervals"* · *"a back test
on the past six months where the project has been working ... how the paper
accounts would actually be better if we did something else"* · *"six of the paper
accounts armed ... compare to normal S&P 500, we don't have to hold it ... different
time intervals, different industries, different stocks ... human decision-making
model"* · *"convert into an app rather than a website ... an X on the PC ... a person
that doesn't have any coding should open it and click ... nightly runs one click ...
see the neural network improving, daily news, past month news, future news ...
multiple separate neural networks for multiple sources ... joined"* · *"update the
night run, make it ready for Opus ... run the night run again for a whole day."*

### 10.1 What is DONE this morning

| item | where | status |
|---|---|---|
| **RW1 randomised-window backtests** | `scripts/night_rw_random_windows.py`, queue job `RW1_random_windows` | **RUN** — 240 seeded windows of 6-72 months anywhere in 1999-2024 × 6 strategies (the fleet's selectors, a human-heuristic proxy, an ensemble, G1's genome) × 2 constructions × a 5-genome random NULL on the same windows; win rates as EXCESS over the null, by length, by start era, by market regime, and **what it held** (sector and size-band shares when it won vs lost). Receipt `RW1_random_windows_run01.json`, per-window table `RW1_windows.parquet`. Numbers in the review §3. |
| the review of the night | `REVIEW_2026-09-09_...` | written: what was wrong (six defects), what to change (the protocol in §10.2) |
| night queue | `scripts/night_factory.py` | RW1 appended; big evidence files gitignored; everything from the night committed |

### 10.2 THE BACKTEST PROTOCOL CHANGES (the answer to "what could have been done better")

1. **No single split decides anything.** DEV/holdout stays for the *claim*; the
   *product* question is answered on **random windows**: a strategy is
   PRODUCT_PROMISING only if its β-matched win rate exceeds the random-genome null
   on the same windows by ≥ 0.15 in **every** start era and at ≥ 3 of 7 lengths,
   **measured on pooled draws, never one draw** (amended 09-09 03:40Z: RW1's second
   draw, seed 20260910, moved a cell's excess by 0.099 on average and 0.150 at
   most — the same size as the rule — so the excess is computed over ≥ 3 draws
   (≥ 720 windows) with the draw-to-draw dispersion printed beside it, and a
   cell passes only if the excess minus that dispersion still clears 0.15).
   RW1 computes the per-draw numbers; G3's fitness becomes the median β-matched
   excess across random DEV windows, not one 202-month number (the 548× was one window).
2. **Every cell is graded against its own matched control, never against zero.**
   D1's placebo was printed and not subtracted (§8.1). The night runner now
   refuses a `PRODUCT_PROMISING` stamp on any event cell without a `vs_control` field.
3. **Era decay is a test, not a sign count** (§8.6, `ERA_DECAYED`).
4. **Gates derive their floors from the window** (§9.2: `min_months` travels).
5. **Costs are a curve, never one number** (D4): 5/10/25 bps × liquidity floors,
   plus borrow on any short leg (still unmodelled — the H5 prereg must add it).
6. **Archive rows are de-duplicated by ancestry** before any "35/35" count.
7. **The fleet is graded as regret, monthly**: what each armed strategy did vs the
   other five vs SPY on the same days (the "past six months" question, 10.4).

### 10.3 THE SIX ARMED BOOKS (Murat: six strategies, SPY as the index, not held)

| book | strategy | horizon / hold / stop | gross target (1x, no margin) | status at 03:15Z 09-09 |
|---|---|---|---|---|
| hack1 | **THEME BASKET** — `theme_basket` brain (the one brain with a positive live counterfactual on the marks: +$3,564 on 7, hit 0.43), shares only | 21 / 5 / 10% | 8 × 12.5% = 100% | **v2 DEPLOYED** (terminal `5705648`; loop redeployed 03:12Z). Worst case −10%. Was the hand-entered SAFE index anchor, manage-only and empty since 09-04. Murat's own decisions still enter through `/api/journal/thesis` and are graded, not traded by a loop. |
| hack2 | **EVENT 5-session** — `post_event_drift`, contract 5/2/8% | 5 / 2 / 8% | 8 × 12.5% = 100% (risk-sized at decision time) | ARMED; enters only within 3 sessions of a print; the 13 qualifying names on 09-08 were refused by the arbiter's evidence verdict — the reasons live in the Railway ledger (ssh host-key blocked from the laptop), so lane **F2** reads them from the loop's next session and drafts the declared threshold |
| hack3 | **TRACKER balanced k=10** | 63 / 21 / 12% | 10 × 10% = 100% (was 83%) | LIVE, 8 positions; the new notional applies from the 09-09 seal |
| hack4 | **TRACKER profit-max k=5**, v2 without `requires_catalyst` | 126 / 42 / **12%** (was 15%, tightened to pay for the 1.00 cap) | 5 × 20% = 100% (was 50%) | **v2 DEPLOYED** (seal-authority + loop redeployed 03:12Z); first non-empty seal is 2026-09-09's. Worst case −12%, inside the 12.5% fleet ceiling |
| hack5 | **CONVEX options** | 21 / 2 / 50% of premium | premium bound 15% of equity (unchanged) | LIVE, 1 position |
| hack6 | **TRACKER diversified k=15** | 42 / 21 / 10% | 15 × 6.67% = 100% (was 90%) | LIVE, 12 positions; new notional from the 09-09 seal |
| benchmark | **SPY index level** — compared, not held | — | — | `crossbook` reads SPY bars |

Alpaca paper allows 4× (buying power ~$395k on ~$99k). **None of it is used:**
every book targets 100% of equity gross, and `tests_smoke_monday` pins "the
gross cap is not LEVERAGE" (≤ 1.0) and a 12.5% fleet worst-case ceiling. Going
to 2× is a separate flip: it doubles every worst case in this table (−20% to
−24% per book, ~−$128k on the fleet) and needs those two pins changed on purpose.

"Different industries" is served inside the tracker screens by sector (the driver
map) rather than by dedicating a book to a sector: RW1 shows every selector's
wins concentrate in Manufacturing/Services small caps, so a sector book would
mostly re-measure the same regime. If Murat wants an explicit sector-rotation
book, hack4 is the slot (Opus lane F4 drafts it as a v3 contract for his flip).

### 10.4 THE PAST-SIX-MONTHS REGRET BACKTEST (Opus lane P6)

Needs the 2025-26 price panel the repo does not have: pull **daily bars
2025-01 → today** for the tracker universe (~774 names) + SPY through the
terminal repo's Alpaca data key (`alpha/broker/alpaca.py` already fetches
`/v2/stocks/bars`; the loops use it every session, so a local pull is the same
credential), store as `backend/data/optimus/prices_2025_26/bars.parquet` with a
receipt. Then replay each of the six mandates monthly from 2026-03-01 on the
sealed books that existed (terminal `state/` seals, `prediction_book` history)
and print: each book's path vs what it actually did vs SPY, the four
counterfactuals per decision (`decision_log`), and the **opportunity capture**
the counterfactual marker already computes (0.55 on hack3). This is also E0's
missing half (2025-26 news CAN be graded once these bars exist).

### 10.5 THE LLM MONTHLY VALIDATION (Opus lane R2, local Qwen, $0)

For 2020-2024 (the only years with both news bodies and CRSP prices: 69,520
docs, C1 already anonymised 4,669 of them): each month, per name with ≥ 3 docs,
the local model reads that month's anonymised digest and states direction +
confidence for the next 1 and 6 months; graded on CRSP with β first, against a
shuffled-digest control (same names, digests from a random other month), and the
AMNESIA-1 memory canary first (real names vs anonymised: if the model scores
better with real names it is recalling, not reading). Monthly and six-monthly
cells, date blocks, three sub-eras. The Qwen throughput (~690 docs/hr) makes
this a ~2-day GPU job; the pilot is one year (2022).

### 10.6 THE MULTI-NETWORK LEARNER (Opus lane N2, the "separate NNs joined")

One network per source, each trained on its own PIT table and graded alone
before any joining: **data-net** (`learner_v2`, the 143-column panel), **news-net**
(text arm on E0's joined rows + C1's curriculum as pre-training only),
**event-net** (N1's event-level learner; H5 is its first candidate, pre-registered
with borrow cost and a drawdown budget), **backtest-net** (the RW1 window table as
features: which regimes a strategy wins in → a router trained on windows, not
names). The **joiner** is a small gating network over the four heads' OOS scores,
fitted walk-forward, and it is only allowed to see heads that cleared their own
control. Progress is a per-head learning curve the app can show (10.7).

### 10.7 AEGIS DESKTOP — the app (Opus lane A, phased; spec, not built yet)

Murat's requirement: an `.exe` on the PC; buttons, no Python commands; anyone
can run it. Design:

- **Shell:** `pywebview` (Python, packaged with PyInstaller into `AegisDesktop.exe`)
  wrapping the existing Next.js build served by the existing FastAPI backend
  (`backend.main:app`) on localhost. No new web stack; the website IS the app.
  Alternative if the Next.js bundle fights PyInstaller: Tauri shell, same backend.
- **Control API (new router `backend/routers/control.py`):** `GET /api/control/services`
  (backend, llama-server, night queue, C1, each with PID and last heartbeat),
  `POST /api/control/run/{job}` (whitelist = the night queue's job ids; spawns the
  subprocess, records the PID, streams its log), `POST /api/control/night`
  (one click: fetch news → run the day/night queue → write the morning report),
  `GET /api/control/fleet` (six books, positions, equity vs SPY, orders working),
  `GET /api/control/balances` (DeepSeek balance file, Alpaca equities),
  `POST /api/control/stop/{pid}` (the STOP file, then kill by PID — never by image).
- **Pages (existing website pages where they exist):** Services · Fleet vs SPY ·
  Night runs (last leaderboard, one-click start, live log) · Networks (per-head
  learning curves from the receipts) · News (today / past month / forward
  calendar of prints, from the corpus + `event_calendar`) · Picks (the 3,056-
  scorecard candidate list, with the human journal form to act) · Regret
  (yesterday's assumptions vs what happened, from `decision_log` grades).
- **Phases:** A0 control router + one-click night (tests for the whitelist and the
  PID discipline) → A1 `pywebview` shell + PyInstaller build, a desktop shortcut
  → A2 Networks/News/Regret pages → A3 the future-news simulation view (the
  night's R2 forecasts, graded each morning).
- Authority: the app runs services and paper books; it never places a real order.

### 10.8 THE DAY RUN (Opus, agents on `model: "opus"`, $0)

Queue for a whole day, in order (STOP file ends it between jobs):

1. RW1 (done this morning; re-run with seed +1 for a second draw) → **RW2**: the
   same windows for N1's `H5|all` event learner and the reaction long-short
   (event-clock books need the daily tape; reuse D1's machinery).
2. **G3 evolve v2** with random-window fitness (10.2 item 1), de-duplicated
   archive, DD budget enforced as a hard refusal.
3. **N2 multi-network** step one: data-net retrained with the event features
   (`learner_v3`), graded alone, both rulers.
4. **P6** regret backtest once the 2025-26 bars land (10.4).
5. **R2 pilot** on the GPU after C1 (10.5), one year.
6. **A0** control router (10.7), tests, no packaging yet.

Attended, Murat only: hack4's v2 flip; hack2's evidence-gate flip; the H5
pre-registration sign-off; the desktop packaging when A1 lands.

## 11. THE 2026-09-09 DAY RUN — receipts

Built and run by Opus 5 on 2026-09-09, $0 of paid LLM (every receipt
`llm_spend_usd: 0.0`; R2 on local Qwen through llama-server). Six new jobs, all
in the night queue and all reachable from the control router's whitelist:
`RW2_event_windows`, `G3_evolve_v2`, `N2_learner_v3`, `P6_bars_and_regret`,
`R2_monthly_llm`, `N1H5_prereg_read`.

### 11.1 RW1 second draw — the protocol cannot yet resolve its own threshold

`RW1_random_windows_run02.json`, seed 20260910, the same 240-window generator.

| | draw 1 | draw 2 |
|---|---|---|
| top cell by excess over the null | `G1_best_dev_genome\|arena_k50_vw` +0.212 | the same cell, +0.362 |
| Spearman rank correlation of the 12 cells | — | **0.741** |
| mean absolute change in a cell's excess | — | **0.099** |
| max absolute change | — | **0.150** |

**§10.2's adopt threshold is "excess over the null ≥ +0.15 in every start
era". The draw-to-draw noise of a 240-window draw is a mean of 0.099 and a max
of 0.150 — the same size as the threshold.** A single draw therefore cannot
adjudicate the rule the protocol was written around. Either the draw count goes
up (RW1 costs 8 minutes, so 1,000+ windows is free) or the rule is read on
POOLED draws with the dispersion printed. Until then, a cell at +0.19 and a
cell at +0.11 are the same cell.

Concretely, the cell §10.1 highlighted — the momentum + revisions + upside blend
in the wide-band broad book, "+0.19 in 2016-2024" — reads **+0.115** on the
second draw, and its overall excess flips from +0.078 to **−0.032**. Same sign
in the late era, half the size, and the overall sign does not survive. The
human-heuristic proxy's 2016-2024 cell is negative in both draws (−0.217,
−0.089), which is the one ordering both draws agree on.

### 11.2 RW2 — the event-clock books on the same windows, with their own control

`RW2_event_windows_run01.json`: 240 windows × 2 signals × 3 liquidity floors ×
3 borrow rates = 4,104 gradings in 127 s. Every cell carries `vs_control` (the
identical pipeline on the +40-session placebo tape, same window). Borrow is
charged daily on the sessions the short leg is open.

At the tradable corner (**$10m/day floor, 200 bps/yr borrow**), median β-matched
annualised, and the share of windows where the arm beats its own control:

| start era | reaction LS | its control | diff | beats control |
|---|---|---|---|---|
| 1999-2007 (n 88) | +22.56 | +0.96 | **+23.62** | 93% |
| 2008-2015 (n 82) | +12.97 | +4.25 | **+6.90** | 88% |
| 2016-2024 (n 70) | −3.67 | +8.02 | **−13.20** | **24%** |

| start era | N1 `H5\|all` LS | its control | diff | beats control |
|---|---|---|---|---|
| 1999-2007 (n 70) | +36.88 | +42.61 | **−2.79** | **44%** |
| 2008-2015 (n 78) | +14.51 | −1.15 | **+19.59** | 80% |
| 2016-2024 (n 59) | +16.32 | +23.88 | **−6.42** | **46%** |

Two readings, both new:

1. **The reaction long-short is not merely decayed after 2016 — its own control
   beats it.** D4 established the effect dies above the $10m floor; RW2 adds
   that in the modern era the dateless placebo earns *more* through the same
   book. That is a construction, and the lane is closed in every form.
2. **H5's pooled "+32.2%/yr t 2.92 after its control" is one era.** On windows,
   the placebo-trained pipeline beats the learner in the earliest and the
   latest era. N1's pooled control comparison could not see that, because a
   pooled t averages over the eras it is made of.

**Borrow is not the binding constraint** — 200 bps/yr moves these cells by about
2 pp. The floor is: at floor $0 the H5 arm shows a median +87%/yr and *its
control shows +18.9%/yr*. Everything interesting below $3m/day is microstructure
that both arms share.

### 11.3 G3 — evolve v2, and a drawdown budget that refused the index

`scripts/night_g3_evolve_v2.py`. Four changes against G1 (§10.2): fitness is the
median β-matched excess over the generation's own bank of 24 random DEV windows
*minus the median of 6 random genomes on the same window*; the archive is one
row per **lineage root** and is re-scored on a 60-window bank drawn from a seed
the search never saw; the drawdown budget is a **refusal before any fitness is
earned**; no holdout is read.

The budget had to be fixed before it could bind. A flat `DD_BUDGET = 0.35` on
the full 1999-2015 DEV path **refused 188 of 207 genomes** in the smoke run —
because the VW market itself drew down **47.2%** over that window, so the
declared budget refuses the benchmark. That is a gate that cannot go green. The
limit now derives from the window:

    limit = max(declared budget, the market's own drawdown on the same window)

which on DEV is 0.4721. A book may lose as much as the index did and no more;
where the market was calmer than 0.35, the declared budget binds instead. Both
numbers are printed in the receipt so the reader sees which clause was active.

Two smaller defects the smoke exposed and the run fixes: at `pop=8` the fixed
"4 elites + 4 fresh" left **zero** slots for children (236 genomes in 236
lineages — crossover was never tested), so the population shape now scales with
`pop`; and ranking a genome by its **best** bank is selection on the outcome, so
the archive ranks on the **median across the banks a genome actually met** and
prints how many that was.

### 11.4 P6 — the 2025-26 price panel exists, and the six books' first real regret

`P6_bars_and_regret_run03.json`, `backend/data/optimus/prices_2025_26/bars.parquet`.

**1,248,370 daily bars, 3,060 symbols, 421 sessions, 2025-01-01..2026-09-08,
zero symbols missing, 32 MB.** The gap that stopped every forward evaluation in
this repo is closed. One venue quirk is recorded: the free SIP plan answers
`403 subscription does not permit querying recent SIP data` for **any** explicit
`end` inside its delay window — including yesterday — but clips the window
itself when `end` is omitted, so the puller sends no `end` and the receipt
reports the last session actually served.

The six paper books, over exactly the sessions each existed (2026-08-28 →
2026-09-05, 6 sessions), against SPY on the same days:

| book | book | SPY | regret |
|---|---|---|---|
| hack3 | **−9.50%** | −0.12% | **−9.38 pp** |
| hack6 | **−8.53%** | −0.12% | **−8.41 pp** |
| hack5 | −3.54% | −0.12% | −3.43 pp |
| hack2 | −1.18% | −0.12% | −1.06 pp |
| hack1 | −1.14% | −0.12% | −1.02 pp |
| hack4 | −0.52% | −0.12% | −0.41 pp |

The first version of that read compared **8 equity points against 62
timestamps** — it filtered `equity` for falsy values and left `timestamp` whole,
so every book was graded over 62 sessions of SPY while its equity covered 8, and
all six read about 9 pp worse than they were. Pair first, then filter.

**What P6 refuses.** A faithful monthly replay of the six mandates over 2025-26
needs the tracker screen's own inputs (targets, consensus, revisions) for
2025-26; the learner panel ends 2024-12 and the candidate snapshots on disk
cover four dates. The replay is refused with that named missing input rather
than run on a proxy. The accounts were created 2026-08-28, so "the past six
months" does not exist for them either.

**And what it warns about.** Every book built from the tracker universe
(`EW_universe` +58.9%, `MOM_12_1` +27.7%, `REV_1M` +81.1%) is drawn from the
**2026-09-01 screen** — every member survived to today. Those rows carry a
`BIAS_WARNING` and are excluded from the headline; the index rows are the only
honest bar. The reversal row is the worst case, because it buys the previous
month's biggest losers, which is precisely the set most likely to have been
delisted. An unbiased 2025-26 replay needs a point-in-time universe vintage per
month. (The first version of `REV_1M` also carried a look-ahead — a formation
window ending at lag 0 meant the signal for month *m* was minus the return *of*
month *m*, and it printed −98.8%. The formation window now refuses any
specification that would read the month it trades.)

**Beta beside the table, and why it refuses.** `P6_bars_and_regret_run04.json`
adds each book's beta against SPY on its own sessions, because a return beside
the index means nothing without the loading that produced it (the 09-07
two-rulers rule). It is **not estimable on this window**: four paired sessions
give hack3 0.413 +/- 0.762, hack6 0.244 +/- 0.253, hack5 0.182 +/- 2.205. Every
standard error is comparable to or larger than its estimate, so the -9.50% and
-8.53% cannot be split into market exposure versus selection. The narrower
statement that IS supported: SPY was flat (-0.12%) across those days, so the
losses did not come from market direction -- they came from the names held and
the cost of entering them. The receipt prints the standard error next to every
beta and says so in the row.

### 11.5 A0 — the control router

`backend/routers/control.py` + `backend/tests/test_control_router_authority.py`
(9 tests). `GET /api/control/{services,jobs,leaderboard,balances,runs/{pid}/log}`,
`POST /api/control/{run/{job},night,stop/{pid},stop-file/clear}`. Three
properties are pinned by AST test rather than intended: no broker or order
symbol is importable; every spawn is an argv list with `shell=False` and a job
id from the queue's **derived** whitelist (a job added to `QUEUE` is a button
without touching the router); and nothing can be killed by image name — only a
PID in the router's own run registry, after the STOP file is written. Every
mutating route refuses with 403 unless `AEGIS_CONTROL_ENABLED=1`, so the router
is inert on the Railway deployment and live only in the desktop shell.

One note on the test itself: its first version grepped the raw source for `/IM`
and failed on the docstring that explains **why** kill-by-image-name is banned.
A gate that fires on its own rationale teaches the reader to delete the
rationale, so it reads the AST and skips docstrings.

### 11.6 N2 — the data-net does not learn from the earnings print

`N2_learner_v3_run01.json`, `scripts/night_n2_learner_v3.py`. The first head of
the multi-network lane (§10.6): the monthly data-net, given the one input it has
never had — what the company's most recent earnings print did (`ev_reaction`,
`ev_z_reaction`, a PIT trailing percentile, SUE, staleness, prints in the
trailing year, the gap column) — beside a control that carries the **same eight
columns drawn from the +40-session placebo tape**, so the comparison is
information, not column count.

Coverage is not the problem: **97.9% of the 925,757 panel rows carry a print
within 400 days, median staleness 46 days.**

Paired month by month over 251 months, top-100 EW, $3m floor, 25 bps a side:

| | β-matched %/yr | t (NW) |
|---|---|---|
| v2, panel only | −10.66 | −2.34 |
| v3, panel + event | −7.84 | −1.64 |
| v3 CONTROL, panel + **dateless** event columns | −8.74 | −1.86 |
| **v3 − v2 (paired)** | **+2.267** | 1.047 |
| **control − v2 (paired)** | **+2.780** | 1.888 |
| **incremental over control** | **−0.513** | — |

**Adding eight dateless columns helps the book by +2.78%/yr; adding the real
earnings print helps it by +2.27%/yr. The print is worth −0.51%/yr against its
own control.** The apparent gain is capacity, not information — a regularisation
effect from widening the feature matrix — and a run without the control arm
would have reported "+2.3%/yr from event features" and been believed. This is
the D1 lesson applied before the fact rather than after it.

`FAILED_VARIANT`. The event-net stays a separate head (N1's lane); it does not
join the data-net. Note also that all three arms **lose to the market** on this
construction (terminal wealth 4.8-8.3 against 14.4 at β ≈ 1.75), so the paired
difference is the only readable quantity here — the level is not a book.

The PIT discipline is pinned by `backend/tests/test_n2_event_features_are_pit.py`
(6 tests): a percentile may not move when a later value is appended, an
announcement dated ON the entry date is not attached, a future print never
reaches a past row, a print older than 400 days is blanked rather than carried,
and a column present on only one tape is dropped from **both** so the control
keeps its shape.

### 11.7 R2 — the model is not remembering, and the panel is the constraint

`R2_monthly_llm_2022_run01.json`, `scripts/night_r2_monthly_llm.py`, local Qwen
through llama-server, **$0.00** (934,340 tokens in / 32,973 out; the same tokens
would have cost $0.20 on DeepSeek). Zero refusals on 2,348 calls.

The design puts the checks in the order that makes them mean something: power
first, then the memory canary, then the read, then the shuffled-digest control.

**Power first.** 2022 with `n_docs >= 3` is 1,054 cells — but 92.5 names inside
one month share that month's market, so the observation unit is the monthly
**date block** (canon §58) and there are **12** of them. Measured dispersion
gives an **MDE of 51.25%/yr**. Nothing a news reader plausibly produces is that
large, so the pilot was exploratory before a single prompt was sent.

**The AMNESIA canary passes.** The same months read twice, once with the real
text and the company's real name and once masked:

| | sign accuracy | long-short %/yr | t (12 blocks) |
|---|---|---|---|
| real names (119 cells) | 0.5259 | +18.68 | 2.34 |
| masked (120 cells) | 0.5391 | +21.46 | 2.48 |

The gap is **−0.0132** — the model does *slightly worse* when it can see who the
company is. There is no evidence it is recalling 2022 from training rather than
reading the text, which is the one thing that would have made the whole lane
uninterpretable.

**The read, against its control.**

| | cells | sign accuracy | long-short %/yr | t (12 blocks) |
|---|---|---|---|---|
| masked digest → direction | 1,054 | 0.5301 | +8.25 | 1.55 |
| **shuffled** digest (control) | 1,054 | 0.5074 | +3.35 | 0.51 |
| **read − control** | — | +0.0227 | **+4.90** | **1.155** |

`UNDERPOWERED, EXPLORATORY`. The model reads slightly better than a digest from
a random other month, and a digest from a random other month still earns
+3.35%/yr — which is the reason the control exists. At 12 blocks and an MDE of
51%/yr, +4.9%/yr t 1.16 is a number, not evidence.

**The binding constraint is the panel, not the model.** `r7_news_representation/panel.parquet`
is 9,457 cells over **135 names and 115 months**, because only 65.4% of the
528,223 documents link to a permno and CRSP's labels stop at 2024-12. Blocks are
what buy power here, so the job now takes a **span** rather than a year: the
2015-2024 read is 7,418 cells over **112 blocks**, which drops the MDE from
51.25%/yr to **18.56%/yr**. That run is the one worth reading; the 2022 receipt
stands as the pilot that measured why.

One join note: the documents carry tickers and the panel is keyed by permno, so
R2 reuses `r7_news_representation.resolve_permnos` — CRSP's point-in-time
`namedt`/`nameenddt` interval join, the same crosswalk the panel was built with.
A flat ticker→permno dictionary would inherit an earlier company's permno for a
reused ticker, which is the share-basis failure this programme already paid for
on 2026-09-04. The first version of this job refused rather than guess; reusing
the panel's own crosswalk was the right answer, and the refusal path is still
there for a checkout without it.

### 11.8 TRIAL-H5 — the one registered read, and the trial closes REJECTED

`N1H5_prereg_read_run01.json`, `scripts/night_h5_prereg_read.py`. The single
historical computation `docs/TRIALS/TRIAL-H5-event-learner-five-session.md`
permits, run once after its commit, on the frozen configuration and nothing
else: hold 5, entry at the close of session +1, featureset `all`, LightGBM 400
trees, purged walk-forward with a 5-session embargo from 2004, PIT rank 63 /
pool 200, top and bottom deciles, 25 bps a side, **100 bps/yr borrow**, $10m to
decide and $3m to report, seeds 0-12.

**Primary — learner minus its placebo-trained control, $10m floor, borrow
charged, 156 monthly blocks:**

| | learner | control | difference | t (NW) |
|---|---|---|---|---|
| **$10m floor (decides)** | +26.31 | **+17.64** | **+20.79%/yr** | **1.142** |
| $3m floor (reports) | +44.94 | +3.27 | +47.02%/yr | 3.03 |

| era | difference | t | months |
|---|---|---|---|
| 2004-2007 | +23.30 | 1.11 | 36 |
| 2008-2015 | **−7.74** | −0.44 | 53 |
| 2016-2024 | +42.00 | 1.12 | 67 |

**REJECTED**, on three independent reject clauses, with **zero of five** adopt
clauses passing:

- `t < 1.5` — **1.142**;
- `the control's own seed-median > +4.0%/yr` — **+17.64%/yr**. At the tradable
  floor the pipeline fed **dateless** events earns +17.6%/yr through the same
  book. That is the clause the registration wrote for exactly this case: *the
  machinery manufactures the spread*;
- `the $10m floor removes more than half of the $3m excess` — **44.2% survives**.

And for completeness the adopt side: the effect is +20.8 against a declared
+31.0; the sign flips in 2008-2015; the drawdown is **−78%** against a −45%
budget; and the RW2 clause fails (§11.2).

The single most informative line is the control's. At $3m it earns +3.27%/yr and
the learner earns +44.94; at $10m the learner falls to +26.31 and **the control
rises to +17.64**. The apparent edge lives below the liquidity floor, and above
it the dateless twin catches most of the way up. N1's headline "+44.5%/yr, control
t −0.45" was a $3m-floor, zero-borrow number; neither of those is the corner the
money would trade in.

Both readings of "seed-median" are printed because they differ and the
conclusion should not depend on the choice: the element-wise median monthly
series gives +20.79%/yr, the median of the thirteen per-seed estimates gives
+9.00%/yr. Both are far below the +31.0 adopt threshold and both reject.

One clause needed an arithmetic fix, recorded as a formal amendment on the trial
(finance `c24492d`) and repeated in the receipt so the two agree: *"the $10m
floor removes more than half of the $3m excess"* is a ratio, and a ratio with a
non-positive denominator is not a fraction of anything — a negative $3m excess
beside a positive $10m one gives a negative ratio and would trip the clause for
the opposite of its purpose. It is now evaluated only where the denominator is
positive and reported `NOT_EVALUATED` otherwise, with the number printed.
Threshold untouched. On this read the denominator is positive, so the clause was
evaluated normally.

`H5|all` goes to `NEGATIVE_RESULTS.md`. The same instrument is not re-run, and
no successor is registered from this session.

### 11.9 RW1 pooled — under the amended rule, nothing passes

`RW1_pooled_run01.json`, `scripts/night_rw1_pooled.py`. Three draws (seeds
20260909 / 20260910 / 20260911), **720 windows**, read under §10.2 as amended:
pool the draws, print the draw-to-draw dispersion per cell, and a cell passes
only if `excess − dispersion` still clears +0.15 **in every start era**.

| cell | pooled excess | dispersion (sd) | excess − sd | eras clearing |
|---|---|---|---|---|
| G1 best DEV genome \| arena_k50_vw | +0.328 | 0.104 | +0.224 | 1 / 3 |
| ensemble_3 \| arena_k50_vw | +0.289 | 0.131 | +0.158 | 1 / 3 |
| G1 best DEV genome \| broad_k100 | +0.188 | 0.057 | +0.131 | 2 / 3 |
| revisions_4w \| arena_k50_vw | +0.162 | 0.071 | +0.090 | 1 / 3 |
| human_heuristic_proxy \| arena_k50_vw | +0.191 | 0.142 | +0.049 | 1 / 3 |
| momentum_12_1 \| arena_k50_vw | +0.107 | 0.075 | +0.032 | 0 / 3 |
| ensemble_3 \| broad_k100 | +0.048 | 0.069 | −0.022 | 0 / 3 |
| target_upside \| broad_k100 | −0.138 | 0.058 | −0.196 | 0 / 3 |

**0 of 12 cells clear the rule.** Per-cell dispersion runs 0.057 to 0.142 on 240
windows a draw, which is why one draw could not adjudicate a +0.15 threshold.
The top row is G1's own DEV genome, which was already read on the holdout and is
not a candidate; the best genuine cell is `ensemble_3|arena_k50_vw` at +0.158
after dispersion, and it clears in one era of three.

The cell §10.1 called this morning's one live signal —
`ensemble_3|broad_k100_ew_hold400_floor3m` — pools to **+0.048 ± 0.069**, i.e.
**−0.022** after dispersion, clearing in **no** era. That reading is now
retracted on three draws rather than argued about on one.

### 11.10 G3 — the archive, and two defects in this job's own design

`G3_evolve_run01.json` + `G3_verdict_amendment.json`. Full 4-hour box:
**437 generations, 2,373 genome-evaluations, 5,348 drawdown refusals (69.3%),
595 distinct genomes collapsing to 251 lineages (0.422).**

| | |
|---|---|
| best on the **selection** banks | +28.637%/yr over the random-genome null |
| best on the **archive** bank (a seed the search never saw) | **+20.261%/yr** |
| shrinkage | **−8.376 pp (29%)** |
| finalists holding up out of bank | **12 of 12** |
| drawdown limit applied | 0.4721 (declared 0.35, market's own −0.4721) |
| holdout | **not read** |

The archive bank is the part worth keeping: twelve lineages, each re-scored on 60
windows drawn from a seed the search never touched, all still positive, losing
29% of their selection-bank excess in the move. Ancestry de-duplication does its
job — a count over this archive is a count over 251 lineages, not over relatives,
which is precisely what G2's "35/35" could not say.

**The verdict is amended from `PRODUCT_PROMISING` to `CONDITIONAL`, for two
defects in this file's own design.** Both are the same shape as the findings the
day run made in other lanes, which is the uncomfortable part.

1. **The null is not held to the arm's own gate.** `WindowBank` draws its six
   null genomes with `random_genome()` and no admissibility check, while every
   scored genome first had to survive the derived drawdown refusal — which
   rejected **69.3%** of candidates. So the fitness is *an admissible genome
   minus a typical genome*, and whatever the drawdown filter selects for beyond
   drawdown itself is credited to the signal. Direction: inflates. Magnitude:
   unmeasured. Fix: one line — apply `admissible()` to the null draws too.
2. **The archive still ranks on one bank of luck.** Ranking by the median across
   banks was the correction to ranking by the best bank — but the receipt's own
   `finalist_basis` reads *"ALL lineages (only 3 met two banks)"*. For nearly
   every lineage the median is a median of **one** draw, so a genome that drew a
   lucky bank still outranks one tested twice. Fix: make `banks_met >= 2` an
   eligibility condition rather than a preference, and re-score surviving elites
   on a fixed audit bank each generation so the count accumulates.

What survives both: the drawdown budget derived from the window is the right
form and it bound hard — 69.3% refused, against the 91% starvation a flat 0.35
produced and the ~0% a penalty term produces. And no holdout was read, so
nothing here has been spent.

### 11.11 What the day run changes, and what to fix next

**Six defects found in this session's own new code**, every one of the same
family as the six the morning review found in the night's:

| where | defect | fixed |
|---|---|---|
| G3 | a flat 0.35 drawdown budget refuses the index itself (market drew −47.2%) | limit derives from the window |
| G3 | at `pop=8`, "4 elites + 4 fresh" left zero slots for children | shape scales with `pop` |
| G3 | ranking a genome by its **best** bank is selection on the outcome | ranks on the median across banks |
| G3 | the null bar is not held to the arm's drawdown gate | **open** — one line |
| G3 | finalists are mostly single-bank | **open** — make `banks_met>=2` eligibility |
| RW2 | windows drawn across a span the loaded tape does not cover | span derives from the tape |
| P6 | `REV_1M` formation window ended at lag 0 — the signal was the month's own return | refuses any window that reads the month it trades |
| P6 | `equity` filtered, `timestamp` not — 8 points graded against 62 sessions of SPY | pair first, then filter |
| P6 | survivor-screen books reported as benchmarks | `BIAS_WARNING`, excluded from the headline |
| N2 | a control with fewer columns than the treatment | columns intersected across both tapes |
| R2 | a pre-hoc MDE 1.61× too conservative stamped a t 3.9 result "underpowered" | realised SE printed beside it |
| leaderboard | `REFUSED` matched inside a sentence about something else; a `\|` in a headline split the row | tag by position, cells escaped |

**The five things worth doing next, in order of what they unblock:**

1. **A point-in-time universe vintage per month for 2025-26.** It is the single
   input blocking the six-mandate replay (§11.4) and it makes every 2025-26
   benchmark honest instead of survivor-screened. Everything P6 refused turns on it.
2. **Widen the joined text-and-return panel.** R2's read is the only positive
   result of the day (+16.19%/yr over its own control, t 3.92 on 112 blocks) and
   it sits on **135 names**. 65.4% of 528,223 documents link to a permno and
   CRSP labels stop at 2024-12; the bars from §11.4 now cover 2025-26, so the
   ceiling is the label join, not the text.
3. **Costs and turnover in R2.** The levels are gross. The primary is a
   difference between two identically-rebalanced books so costs largely cancel,
   but that is an argument, not a measurement.
4. **The two G3 one-liners**, then the §10.2 era rule on the survivors.
5. **Pre-register R2's prompt and digest construction** before widening it. The
   prompt was not registered, and it is now the only live lane.
