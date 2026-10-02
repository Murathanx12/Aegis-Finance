# hyp_lab: a hypothesis ledger that learns, and its first eight cells (night of 2026-09-29)

Licence `PRODUCT_EXPERIMENT`. Nothing here trades or changes a book, a weight or an order.
**The night was paused by the owner at about 22:45 local.** Everything below was finished before the
pause. The LLM-theory arms (JOB 3) and the nn_lab work (JOB 4) ran in parallel and have their own
notes (`llm_theories_2026-09-30.md`, `nn_lab_size_members_2026-09-30.md`) if they were written
before the pause. Their numbers are NOT restated here.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** Eight pre-declared cells ran. None is `CONDITIONAL_POSITIVE`.

| line | tonight |
|---|---|
| Best historical net strategy vs market | unchanged (none) |
| Best forward paper strategy | unchanged (none graded) |
| Independent selector count | unchanged |
| Candidates tested / promoted | 8 hypothesis cells / 0 promoted: **4 FAILED_VARIANT, 4 CANNOT_DISTINGUISH** |
| New actionable finding | (1) Text co-mention links carry **less** same-session read-through than return-correlation peers, and neither carries anything into the next session. (2) The earnings size fact replicates in 2025 (+0.29 log ratio, t 5.2, 12 of 12 months), but it adds **no** IC over trailing vol + TF-IDF. (3) Regional banks' response to yield shocks **flipped sign** between 2016-22 and 2023-26. |
| Hypothesis ledger | **42 rows**: 8 run, 17 queued runnable, 12 need a cell or forward time, 5 duplicates. Sources: 15 seeded, 17 DeepSeek-generated, 8 local-7B-generated, 2 derived from tonight's verdicts. |
| LLM spend (whole night, all hyp_lab-owned calls, the shared file `hyp_lab/spend.jsonl`) | **$0.61 ledger / $1.51 at peak list price** against the $3.00 cap. Almost all of it is the JOB 3 arms (12,688 calls). Generation cost $0.004 ledger for 2 calls. The provider balance was **$25.02** at the start (snapshot `hyp_lab_night_20260929_start`). The end snapshot was **not taken**, because the pause forbids network calls. |
| Cost per gradeable output | $0 for the cells (CPU only) |

## 1. What was built (JOB 1)

| file | what |
|---|---|
| `backend/services/hyp_lab.py` | The ledger: typed rows (mechanism, precursor known beforehand, separation from beta, refutation, target, family, data, cell type + params, declared split), an append-only event log, dedupe against `docs/TRIALS` + the closed LLM list + the ledger, per-family learning, EV ranking, declaration receipts with sha256, a runner that writes verdicts back, the generation prompt, and a markdown view. |
| `backend/services/hyp_cells.py` | Three parameterised designs that run unattended: `macro_lead_lag`, `event_readthrough` and `size_feature_increment`. There is **one verdict rule** for all of them: the design fold fixes the sign, and the confirm fold decides. |
| `backend/services/hyp_llm.py` | The one budgeted call path. It goes through `llm_analyzer.call_named` and appends every call to `hyp_lab/spend.jsonl` with the ledger cost AND a peak-list-price estimate. The per-night cap is re-read from the file before each DeepSeek call, so it is shared across processes. A night ends at 08:00 local. |
| `scripts/hyp_lab.py` | The CLI: `seed`, `generate`, `rank`, `declare`, `run`, `t2`, `nightly` and `schtasks`. |
| `backend/tests/test_hyp_lab.py` | 20 offline tests, all passing. |
| `backend/config.py` | An appended `HYP_LAB_*` block: night cap $3.00, nightly cap $0.40, at most 8 cells a night, a free-memory floor. |
| `docs/TRIALS/TRIAL-HYP-LAB-NIGHT-1-readthrough-attention-size-cells.md` | Registration of tonight's eight cells. |
| Scheduled task `AegisHypLabNightly` | Daily at 09:30 local, after nn_lab at 08:30. It runs `run_nightly.cmd`, which refuses on the STOP file. **It is DISABLED by the owner's pause. Leave it that way until he says continue.** |

The tests cover:
- the ledger: discard without a refutation, an id per parameter set, an append-only fold, and duplicates by text and by params;
- the loop: family learning moves the queue, and value comes from the cell rather than from the generator's claim;
- the run path: the declaration receipt exists before the runner is called, and the STOP file and a crashed cell both refuse;
- the budget: the cap binds even when the ledger prices a call at $0, and truncated JSON is recovered;
- the cells, on synthetic data:
  - a planted lag is found, and a same-day-only link is not;
  - co-mention links never use a document known on or after t;
  - correlation peers exclude the source and the index.

`signal_reachability`: all three modules are reachable from `scripts/` (tooling tier).

**How it learns.**
- Each family gets a Beta(1,4) prior on P(conditional positive), updated by verdicts. A CANNOT_DISTINGUISH counts as half a failure.
- `EV = power x [P(pos) + (1 - P(pos)) x w_neg] x value x novelty - cost`.
- The generation prompt carries every verdict and the family record. After tonight's run the size families fell from P 0.20 to about 0.14-0.17, so the queue moved.
- Generated rows are validated against the bars panel. Two local-7B rows named non-equity targets and were parked as NEEDS_CELL. One DeepSeek row mixed opposite-signed mechanisms in one basket and was parked by human review, with the reason recorded in the ledger.
- Dedupe threshold: cosine 0.09 against the closed corpus. It was calibrated on four known duplicates (0.10-0.32) and unrelated rows (0.02-0.06). It is a TF-IDF heuristic and it misses paraphrases.

## 2. Tonight's verdicts (JOB 2)

The cells were declared before they ran: `hyp_lab/receipts/declare_20260929T133917Z.json`, sha256 `5a15f7bf…4e90`. That receipt discloses two earlier smoke looks and the reason for the slot-8 choice. Each cell has a receipt `hyp_lab/receipts/cell_<id>_*.json`. The standard error is taken over month blocks for the macro shocks and over week blocks otherwise, and MDE = 2.8 SE.

| hyp_id | cell | design fold | confirm fold (decides) | verdict |
|---|---|---|---|---|
| H-c12383c5f7 | oil shock -> airlines, next session, residual of beta | -0.23% (t -0.94, 97 shocks) | +0.35% (t 1.10, MDE 0.90%, 57 shocks) | CANNOT_DISTINGUISH |
| H-fc9a95991b | 10-y yield shock -> regional banks, next session | **-0.27% (t -1.36)**; same day banks move **with** yields (t 6.7) | **+0.41% (t 2.15, MDE 0.54%)**, in the digest's direction | CANNOT_DISTINGUISH (the sign flipped) |
| H-f4c998e55b | yield shock -> REITs, 5 sessions (DeepSeek-generated) | +0.23% (t 1.03) | -0.004% (t -0.01) | FAILED_VARIANT |
| H-4d7c66c90d | earnings reaction >= 2x vol -> text co-mentioned names, next-session log size vs vol-matched | +0.035 (t 0.34, 232 events) | +0.029 (t 0.39, MDE 0.21, 324 events) | CANNOT_DISTINGUISH |
| H-242b74a461 | same events -> 5 correlation peers (the factor-beta link) | +0.013 (t 0.30, 628) | +0.044 (t 1.29, MDE 0.095, 774) | CANNOT_DISTINGUISH |
| H-0508c8b2b4 | abnormal attention over T2 (priors + TF-IDF), size IC | -0.0014 (t -4.24) | -0.0011 (t -1.72, MDE 0.0017) | FAILED_VARIANT |
| H-d90a84da8c | cross-source tone disagreement over T2 | -0.0007 (t -2.94) | -0.0001 (t -0.40, MDE 0.0009) | FAILED_VARIANT |
| H-57ab67541e | event-type size prior over T2, with 2025 H2 as the second fold | -0.0009 (t -1.08) | +0.0001 (t 0.31, MDE 0.0009) | FAILED_VARIANT |

### What the numbers say beyond the verdicts (reported, not deciding)

**Read-through happens the same day and is gone by the next.**
- Correlation peers move with the source on the reaction session: signed +0.65% (2025) and +0.93% (2026), t 7.7 and 8.3. Their size is +0.21 and +0.19 log ratio over vol-matched names.
- Text co-mention links are weaker on that same session: signed +0.17% and +0.41% (t 0.6 and 1.2), size +0.29 (t 3.1) and +0.16 (t 1.1).
- At t+1 neither link type moves beyond its own volatility, and the direction is about zero for both (|t| < 0.8).
- So the digest's second-order read-through is priced within the session, and the news graph adds nothing over plain return correlation. This agrees with MARKET-GRAPH-1 (co-movement real, portfolio route closed) and with W4b.
- The limit: the source events are the student's `earnings_report` labels on first documents, so only 232 and 324 events had a text link.

**Attention is information the base model already has.**
- On its own, `abn_attention` has IC +0.073 with |move| and +0.10 with move/vol on the 2026 test block.
- Adding it to T2 lowers IC slightly. The base already holds the document and source counts and the words.
- Every size cell picked the largest ridge penalty on validation, which means "use none of it".

**Earnings replicates as a risk fact, not as an increment.**
- Relative size of earnings cells over no_event cells (`supp_event_rel_by_year.json`): 2025 **+0.29** (t 5.2, 12 of 12 months), 2025 H2 +0.21 (t 2.2, 6 of 6), 2026 +0.22 (t 5.1, 9 of 9).
- Guidance changes: +0.37 in 2025 (t 4.4) and +0.17 in 2026 (t 1.8).
- TF-IDF already carries this through the words, which is why the prior adds no IC.
- It is still a fact an options desk can use. See the queued row H-3336ff8cdd (earnings/guidance vs the implied move on the straddle log).

**Regional banks: a regime flip, found after looking.**
- 2016-22: banks rose with yields on the day and drifted slightly back the next session.
- 2023-26: the same-day link is near zero, and the next session falls after a spike (t 2.15).
- It is logged as H-575b8c97c1, a forward-only row, because the confirm data are now seen. It gets about 12 shocks a year, so a verdict needs about two years.

**Multiplicity.** Eight cells plus two smoke looks. One t >= 2 line among them (the banks' confirm fold, with the design sign opposite) is what chance produces.

## 3. JOB 3 / JOB 4 / JOB 5 at the pause

- JOB 3 (LLM theories: blinded size and pairwise questions, numbers vs numbers+LLM, self-consistency; DeepSeek, local 7B, 1.5B):
  - It ran about 12,700 DeepSeek calls and 564 local calls through `hyp_llm` ($0.61 ledger / $1.50 peak). Receipts are `hyp_lab/job3_*`.
  - Its skill table is in its own note and report. It is not restated here.
- JOB 4 (nn_lab: ETFs out, deaths after 2022, raw prices, TF-IDF and earnings size members):
  - Its own note and report cover it.
  - `AegisNNLabNightly` is disabled by the pause.
- JOB 5 (bulk event conversion): **not started.** The local graphics card was held by JOB 3 until the pause.

## CONTINUE FROM HERE (only after the owner says continue)

```powershell
# from the repo root; remove the pause first
Remove-Item backend\data\optimus\hyp_lab\STOP
$env:AEGIS_PERSONAL_MODE="0"
.venv\Scripts\python.exe -m scripts.hyp_lab rank --runnable            # the queue (LEDGER.md is rewritten)
.venv\Scripts\python.exe -m scripts.hyp_lab nightly --k 3 --cap 0.40   # generate -> dedupe -> declare -> run
schtasks /Change /TN AegisHypLabNightly /ENABLE                        # only with the owner's go
# the DeepSeek balance end-snapshot owed for this night:
.venv\Scripts\python.exe -c "from backend.services import deepseek_balance as B; print(B.snapshot('hyp_lab_night_20260929_end'))"
# JOB 5 (local graphics card, $0, resumable; record the CHILD PID; stop with ft_lab\runs\STOP):
Start-Process ft_lab\.venv\Scripts\python.exe -ArgumentList "-m","ft_lab.bulk_events","--minutes","80" -RedirectStandardOutput ft_lab\runs\bulk_events.log -RedirectStandardError ft_lab\runs\bulk_events.log.err -WindowStyle Hidden -PassThru
# tests
$env:AEGIS_IGNORE_DOTENV="1"; .venv\Scripts\python.exe -m pytest backend/tests/test_hyp_lab.py -q -p no:cacheprovider
```

The top of the queue now:
1. AI-leader shock -> semi equipment (seeded from the digest).
2. Oil shock -> tanker stocks (DeepSeek).
3. Yield -> utilities.
4. Yield -> homebuilders.
5. Yield -> money-centre banks (DeepSeek).

All of them are macro lead-lags. Tonight's two macro lead-lags showed no lag, and the family's P has already been cut. Two nights of FAILED/CD on this family will push the size and read-through NEEDS_CELL items up.

## WHAT WORKS

- A typed ledger with a hashed declaration before every run. Verdicts are written back and read by the next generation, and the queue moves when a family fails.
- The per-night dollar cap shared across processes through one spend file. It binds at the peak list price even when the ledger says $0.
- Cheap and fast unattended designs: eight cells ran in about 10 minutes of CPU, most of it waiting for free memory.
- DeepSeek as a hypothesis generator: 17 rows, all with a refutation, and most mapped to a runnable cell.

## WHAT DOES NOT

- Next-session read-through: from an earnings shock to linked names, by text or by correlation, and from oil or yield shocks to exposed baskets. It is priced the same session.
- News attention, cross-source disagreement and event type as size features over trailing vol + TF-IDF. Each is informative alone and redundant with the base.
- The local 7B as a hypothesis generator. Its rows were generic, 2 of 8 named non-equity targets, and 2 were duplicates.
- Mixed-sign baskets from the generator. They need the human-review guard that caught one tonight.

## HIGHEST-EV EXPERIMENT

**Stop testing lags and test the one number that already replicates against the market's own price for it.**
- Earnings and guidance cells move 0.2-0.37 log units more than trailing vol predicts, in every month of 2025 and 2026.
- The open question is whether the options market already prices this.
- Join the straddle forward log (TRIAL-STRADDLE-FWD-1, first entry 2026-10-16) to the student's event types and read realised/implied for earnings-flagged entries versus the rest (ledger row H-3336ff8cdd).
- It costs $0, the data accrue anyway, and it is the only route by which tonight's replicated fact could become money.

## Addendum after the pause: Job 3 and Job 4 results (details in their own notes)

- **Job 3 (LLM theories, `llm_theories_2026-09-30.md`): no LLM arm added anything over the numbers for the size of the next move.**
  - Q1, forced probability that the move beats the stock's typical move: both text arms abstained. DeepSeek's Brier was 0.2442 against 0.2437 for the numbers model (difference t −0.03). The 7B answered 0.45 on 237 of 240 items.
  - Q2, which of two masked names moves more:
    - DeepSeek on text alone got 55.9% right, against 62.3% for "pick the higher-volatility name".
    - With the numbers in the prompt it got 64.6%, the same as the pair-numbers model in Brier (t −0.76).
    - The 7B was at a coin.
  - Q3, forced ranking of 8 same-date items: DeepSeek's IC on the relative move was +0.042 (t 2.09). On the residual of the numbers model it was +0.004 (MDE 0.049), so the numbers already hold it.
  - Stacking and self-consistency added nothing measurable.
  - Leak checks: 1.7-9.9% of items identified; dropping them changes no sign.
  - Two closed rows were appended to the ledger (now 44 rows).
- **Job 4 (nn_lab, `nn_lab_size_members_2026-09-30.md`):**
  - An earnings release expected in the hold window (from 8-K cadence, known beforehand) adds **+0.0067 IC to the 5-session size forecast (t 5.76, positive 6 of 7 years)**, and +0.0051 over the fitted ridge baseline. It is in the nightly at weight 0.
  - The text member hurts over 5-21 sessions.
  - ETFs and ETNs are out, and CRSP deaths for 2016-24 are recovered. The rebuilt table is live behind the nn_lab STOP file.
- **Spend at the pause:** $0.61 by the ledger, $1.51 at peak list price, against the $3.00 night cap.

---

# Second shift, 2026-09-30 00:00-08:30 local: why the twin trails the market, the investable versions, risk as the product

Licence `PRODUCT_EXPERIMENT`. No book, order, weight or live contract was changed.

- **Registrations: none (no shadow contract).**
- One forward trial file was written, for an underpowered source (§5).
- Receipts are under `backend/data/optimus/hyp_lab/`.
- The run tags (`INV_…T0020Z`, `RS_…`, `VM_…`, `IE_…`) are labels, not UTC times. Each receipt carries its
  own `written_utc`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** Nothing survives against the market, whether as a long book, a hedged spread
or an overlay. The night did answer the honest question, and the answer corrects the board.

| line | tonight |
|---|---|
| Best historical net strategy vs market | Unchanged: none. **0 of 22** declared spread/overlay cells, **0 of 8** vol-managed cells and **0 of 8** insider-event cells survive. |
| Best forward paper strategy | Unchanged (nothing graded). |
| Independent selector count | Unchanged. |
| New actionable finding | **The twin drag is a cost convention, not a portfolio.** The matched twin is charged a full spread round trip every month, while a rule pays only its own turnover. On the board's declared variant, **106 of 161 rules beat their twin at t >= 2. On gross selection alone, 18 do.** The median inflation is **+0.45%/mo**. |
| Second finding | The insider cluster drift is real gross: +1.1 to +1.5% over 5 sessions vs same-band names, t 3.9-6.4 in every era. It **equals the spread** (136 bps mean round trip). In names that are cheap to trade, the drift is absent. |
| Restatement | Does not move the ranking. FIRST minus LATEST vintage: -0.003%/mo for quality (MDE 0.075), -0.027%/mo for cash_lowvol (MDE 0.060). The picks overlap 98-99%. |
| Search count | **42,705** = 42,666 + 19 investable cells + 8 vol-managed + 8 insider event + 3 ledger nightly cells + 1 forward trial. The fair-twin re-score and the decomposition are transformations of rules already run, not new searches. |
| LLM spend | See the closing addendum (provider balance reconciled). |
| Local graphics card | Bulk event conversion ran inside a time box (§7). |

## 1. Why the matched twin trails the market

Receipt: `investable_decompose_INV_2026-09-30T0020Z.json`. The declaration
`investable_DECLARATION_INV_2026-09-30T0020Z.json` (sha `c76ff99faf23691d`) was written **before** the
decomposition ran. All figures are %/mo, keyed on the hold month, with t on 3-month blocks.

The table shows the validate window (2009-2016), with the full window (1991-2024) in brackets.

| piece | quality_composite | cash_lowvol | ope_be |
|---|---:|---:|---:|
| **Eligibility filters:** value-weighted eligible universe - market | +0.01 (+0.00) | same | same |
| **Equal weighting / size:** equal-weight - value-weight | +0.19 (+0.02) | same | same |
| **Cell mix:** the twin's cells - equal-weight universe | -0.10 (+0.06) | -0.18 (+0.04) | +0.01 (+0.07) |
| **Twin basket GROSS - market** (sum of the three) | **+0.10 (+0.08)** | +0.01 (+0.06) | +0.21 (+0.09) |
| Delisting rows' contribution to the equal-weight universe | +0.00 (+0.00) | | |
| **The board's twin cost:** one full round trip on the twin's names | **-0.69** (-0.73) | -0.59 (-0.63) | -0.82 (-0.82) |
| **The quoted drag:** library twin21 net - market | -0.62 (-0.67) | -0.55 (-0.56) | -0.54 (-0.69) |
| Library twin21 net - twin basket gross | -0.72 (-0.75) | -0.56 (-0.62) | -0.75 (-0.78) |
| **Pure selection:** rule gross - twin basket gross | **+0.06 (+0.20, t 1.6)** | +0.13 (+0.24, t 2.3) | +0.42 (+0.24, t 2.0) |
| Rule net - market, costs at actual traded weight x max(CS, flat)/2 | +0.08 (+0.18) | +0.05 (+0.19) | +0.49 (+0.20) |

**Answer.**

- The twin's portfolio is not bad: gross, it tracks the market within about 0.1%/mo.
- Eligibility filters, equal weighting and delisting returns together explain about 0.
- The whole 0.6%/mo drag is the **cost convention**:
  - the twin is redrawn from scratch every month and charged a full round trip, 0.6-0.8%/mo in small and
    mid names;
  - the rule is charged only its own 11-17% turnover.
- So a "beats its twin" number mostly measures a low-turnover rule against a 100%-turnover benchmark.

**Across the whole CRSP board.** Records are in `twin_board_TB_2026-09-30_1.jsonl`, the table in
`twin_board_TB_2026-09-30_1_table.csv`, and the summary in `twin_board_SUMMARY_TB_2026-09-30_1.json`.

| comparison | rules at t >= 2 (full sample) |
|---|---:|
| 161 EVT/BR rules, the declared board variant (turnover-scaled rule vs full-CS twin) | **106** |
| the same 161 rules, pure selection (gross vs gross) | **18** |
| (turnover for the declared variant is this engine's measured monthly turnover per rule) | |
| the same 161 rules, fair twin (twin basket held and charged its own turnover) | 22 |
| all 301 rules, flat-cost board (both sides pay band costs at their own turnover) | 31 |
| all 301 rules, pure selection | 29 |
| all 301 rules, net - market at t >= 2 in validate | 1 (`qc761_ebit_ev_ebit_ic_large_annual`, see §2) |

- **Median inflation** of the declared variant over pure selection: **+0.45%/mo**.
- **Where the artefact came from.** The flat-cost board (the 133 LIB rules) was fair: its median gap to the
  fair twin is +0.007%/mo. The artefact entered with the turnover-scaled Corwin-Schultz read of the EVT and
  BR boards.
- **The two "SURVIVES" verdicts of 2026-09-30 (`quality_composite`, `cash_lowvol`) rest on this
  artefact.**
  - Their pure selection is t 1.6 and t 2.3.
  - Both are re-read as CANNOT_DISTINGUISH as relative rankings.
  - They were never an edge against the market.
- **Still real as relative rankings** (pure selection t >= 2.5, full sample):
  - `net_raises_trend` 3.8
  - `mom_flow_trend` 3.2
  - `ear_flow` 2.9
  - `trend_quality_trend` 2.8
  - `px_vs_ma200_large` 2.7
  - `flow_in_winners` 2.7
  - `net_raises` 2.6
  - `quality_composite_secrel` 2.5

  That is the revision family again, which agrees with the conditionals.

## 2. The investable versions (`investable_RESULTS_INV_2026-09-30T0020Z.json`, read once)

**The declared line.** A variant survives only if all three hold:

- design mean > 0;
- validate mean > 0 at t >= 2;
- a majority of the 8 validate years are positive.

**What the declaration stated beforehand:**

- The four leads were chosen after their windows were partly seen. Variants A and C are therefore
  implementation reads; B, D and E are new constructions.
- Costs:
  - long legs pay traded weight x max(CS, flat)/2;
  - a short stock leg pays its own trade cost plus borrow of 0.25/0.30/0.60/1.50%/yr for
    mega/large/mid/small;
  - a short size index pays 0.35%/yr;
  - a futures hedge pays 0.12%/yr.

**Validate 2009-2016, %/mo** (t, then validate years positive where given):

| candidate | A: long - market | B: beta-hedged | C: long - short twin basket | D: long - short band index | E: top-500 overlay - market |
|---|---|---|---|---|---|
| quality_composite | +0.08 t 0.38 (4/8) | +0.28 t 1.48 (5/8) | -0.40 t -2.03 | -0.13 t -0.63 | -0.06 t -0.78 |
| cash_lowvol | +0.05 t 0.28 (5/8) | +0.22 t 1.36 (**7/8**) | -0.27 t -1.53 | -0.08 t -0.36 | -0.05 t -0.69 |
| ope_be | **+0.49 t 1.83** (5/8) | +0.24 t 0.90 | -0.14 t -0.55 | +0.31 t 1.23 | -0.03 t -0.50 |
| revision, trend-on, small caps | +0.31 t 1.58 (**7/8**) | +0.23 t 1.19 (7/8) | -0.18 t -1.22 | +0.07 t 0.49 | not run (the top-500 revision tilt is already FAILED_VARIANT) |

**Risk, cost and capacity:**

| candidate | MDE (%/mo) | max drawdown of the B spread, validate / full | turnover/mo | cost bps/mo | $100M as % of median pick ADV (2010s) |
|---|---:|---|---:|---:|---:|
| quality_composite | 0.45-0.60 | -13% / -51% | 14% | 10 | 14% |
| cash_lowvol | 0.45-0.60 | -8% / -26% | 17% | 11 | 7% |
| ope_be | 0.45-0.60 | -15% / -58% | 16% | 13 | 11% |
| revision, trend-on, small caps | 0.40-0.55 | -11% / -31% | 50% | 43 | 13% |

**What the table says:**

- **Shorting the twin loses everywhere.** Its gross edge (0.1-0.4%/mo) is smaller than the short leg's
  trade cost plus borrow (about 0.4%/mo).
- **Beta hedging** is the only construction that is positive in both design and validate for all four.
  None reaches t 2.
- **The closest misses:**
  - `cash_lowvol` B: full 1991-2024 **+0.30%/mo, t 2.65**; validate 7 of 8 years positive;
  - the revision cell A: 7 of 8 validate years positive.
- **2017-2024** is flat or negative for all but `ope_be` D (+0.21) and `quality_composite` B (+0.11).
- **Nothing is registered.**

**One near-miss from the fair-twin re-score, not registered.** On my engine, `qc761_ebit_ev_ebit_ic_large_annual`
shows validate net - market +0.46%/mo, t 2.34; design +0.09 (t 0.65); late +0.10.

- That read was not declared as a validation read.
- The declared board read of the same rule was t 1.01.
- Two engines that disagree are a warning, not a candidate.

## 3. Restatement (`restatement_RESULTS_RS_2026-09-30T0050Z.json`, declaration sha `69b06304422948dd`)

**Data.** The SEC companyfacts history (2009 onward): 24,620 firm-years and 2,068 permnos, linked CIK ->
gvkey -> CCM. Both vintages are timed at the first filing + 2 days, on identical coverage.

Share of firm-years whose value changed by more than 1% between the first and the latest filing:

- revenue 3.9%, COGS 4.6%, operating income 5.4%;
- assets, equity, cash and debt 0.2-0.4%.

| 2010-2024 | quality_composite | cash_lowvol |
|---|---|---|
| rule - twin gross: FIRST / LATEST / Compustat | +0.23 / +0.23 / +0.15 | +0.27 / +0.30 / +0.04 |
| **paired FIRST - LATEST** | **-0.003 (t -0.11, MDE 0.075)** | **-0.027 (t -1.25, MDE 0.060)** |
| pick overlap, FIRST vs LATEST | 97.7% | 99.4% |

**Verdict: restatement does not measurably move either ranking.** The t of 6 came from the twin's costs
(§1), not from restated data.

**Limits:**

- The SEC universe is today's tickers (survivor-selected). This touches all three vintages alike.
- SEC "latest" is a proxy for Compustat's current vintage, not the same file.

## 4. Risk as the product: volatility-managed market exposure

Receipt: `volmanaged_RESULTS_VM_2026-09-30T0115Z.json` (sha `2f172790b925bfc1`).

**Prior closures, read first:**

- Moreira-Muir alpha: refuted 0-3.
- N12 matched-vol log wealth: NOT_DETECTABLE.
- T6: survivor-inflated.

**What is new is the forecaster:**

- HAR, fitted only on 1991-2008;
- HAR plus the earnings-season intensity: the share of market value expected to report inside the hold
  window, taken from each firm's report date a year earlier.

**Construction:**

- Exposure = c / sigma_hat, capped at 2. c is set so that the design-window mean exposure is 1.
- Costs: 2 bps per unit of exposure change, and 0.5%/yr over rf on leverage.
- The benchmark is buy-and-hold at the **same mean exposure**. Matched realised vol is printed beside it.

| cell (monthly rebalance) | validate diff in log utility, %/mo | t | years + | max DD, policy / bench | QLIKE, validate |
|---|---:|---:|---|---|---:|
| rv22 | -0.095 | -0.50 | 4/8 | -16% / -25% | 0.419 |
| rv63 | -0.095 | -0.57 | 3/8 | -17% / -24% | 0.346 |
| HAR | -0.064 | -0.37 | 4/8 | -16% / -25% | **0.309** |
| HAR + earnings intensity | -0.076 | -0.42 | 4/8 | -16% / -25% | 0.325 |
| weekly rebalance (all four) | -0.21 to -0.33 | -1.3 to -1.9 | 0-1/8 | -18% / -25% | 0.44-0.52 |

**Full 1991-2024, monthly rebalance:**

- Terminal wealth equals buy-and-hold at equal exposure: 36.4 vs 35.1 for rv22.
- Sharpe 0.65 vs 0.54.
- **Max drawdown -33% vs -54%.**
- The whole design-window gain (+0.16%/mo) comes from 2000-02 and 2008. This is drawdown control at flat log
  utility, exactly the canon's lesson 3.

**The engine's forecast does not help:**

- HAR forecasts better (QLIKE 0.309 vs 0.419), but HAR - rv22 in policy utility is only +0.06%/mo
  (t 1.76).
- The earnings intensity gets a positive coefficient but worsens QLIKE out of sample. HAR+EI - HAR is
  -0.006%/mo.
- A better size forecast does not become a better book-level exposure policy.

**Verdict: FAILED_VARIANT for log utility.** The drawdown result is a legitimate product question for the
*preservation* personality, but only under a utility declared first. It is logged as H-1270b5a351.

## 5. Insider cluster buys as a daily event study, and politicians

Receipt: `insider_events_RESULTS_IE_2026-09-30T0135Z.json`.

**Data and events:**

- Tonight's live `insider_tx` table holds 7 days, which gives no power. The history used instead is
  `insider_events_v1`: Form 4, 2006-2026, with the observed date taken as the filing date.
- An event is 3 or more distinct officer/director open-market buyers inside 30 days, with a 90-day
  refractory period. That gives **12,333 events**, 85% of them in small names.
- Entry is at the **open** of the next session. The round trip is max(CS, flat): 136 bps on average.

| cell | design net | validate net | t (MDE) | years + | late net | validate gross |
|---|---:|---:|---|---|---:|---:|
| H5 vs market | -0.10 | +0.24 | 1.22 (0.54) | 5/8 | -0.35 | +1.49 (t 6.3) |
| H5 vs same-band EW | -0.08 | +0.01 | 0.06 (0.47) | 3/8 | -0.32 | +1.26 (t 6.4) |
| H21 vs market | -0.07 | +1.03 | **2.23** (1.29) | 5/8 | -0.31 | +2.28 |
| H21 vs same-band EW | -0.07 | +0.16 | 0.55 (0.79) | 3/8 | -0.17 | +1.41 |

**Reading:**

- H21 vs market reaches t 2.23 but fails the design condition. It is also the 2009-2016 small-cap premium:
  against same-band names it is +0.16.
- **The low-cost follow-up.** It was declared after the aggregate read; the subset itself had not been
  read (sha `d95d3e38f38c5d22`).
  - 1,630 events with a round trip of 40 bps or less (mean 35).
  - The 5-session gross drift **vanishes** there: validate -0.53 vs the band, net -0.88 (t -2.24).
- **Verdict: CANNOT_DISTINGUISH net.** The drift lives exactly where the spread is.
- The only route left is execution: paying less than the spread. That needs a forward fill log, not a
  backtest (H-3aac7667ef).

**Politicians.**

- The table holds 855 rows over 74 days of disclosures: 279 common-stock purchases, 88% in the $1k-15k
  bracket, with a median lag of 23 days.
- Instead of reading them, I wrote `docs/TRIALS/TRIAL-CONGRESS-PTR-FWD-1-house-purchase-disclosures.md`:
  - entry at the next open after `tradable_from_utc`, held 20 sessions, measured against SPY;
  - first (description-only) read **2027-04-01**, decision read **2028-04-01**.
- The Aegis-module linter returned **UNPOWERED_AT_REGISTRATION**. With a disclosure week as the dependence
  unit, the smallest effect it can resolve by 2028 is 5.2pp.
  - The file records this verdict and registers the accrual only.
  - A later null there can only be NOT_DETECTABLE.
- The registry row (`rule_experiments`) is left to the integrator, with the commit.

## 6. nn_lab and the hypothesis ledger

### nn_lab (checked, not run)

- `refuse_reason()` returns None, and there is no STOP file.
- The table is the rebuilt one: 1,198,474 rows, CRSP deaths on, ETFs out.
- The MAGNITUDE roster is `trailing_vol, ridge_abs, nn_width, vol_earn`.
- The TF-IDF member `vol_text` is **deliberately not rostered**: it measured negative at h5 and h21.
- `AegisNNLabNightly` is enabled for 08:30. That is after this report, so its receipt is still owed:
  `backend/data/optimus/nn_lab/receipts/nightly_<stamp>.json` and `local_pc/nn_lab/nightly.log`.
- `nn_lab/fetch_assets.py` (the stray module that broke the reachability test) now has a `main()` and does
  nothing on import. Test: `nn_lab/tests/test_fetch_assets.py`.

### The hypothesis ledger (run once by hand, with the scheduled task's own `run_nightly.cmd`)

- STOP was lifted for the run and **put back afterwards**, so the 09:30 task will REFUSE until the owner
  removes it.
- Receipt: `receipts/nightly_20260929T161423Z.json`.
- **Generation:** DeepSeek, 8 rows, $0.0028 against its $0.40 run cap. The served model was
  `deepseek-flash`. The local provider was skipped because its server was not up.
- **Ranked, declared and ran 3 cells** (declare receipt `declare_20260929T161437Z.json`). All three are
  FAILED_VARIANT; confirm-fold means in %/day:
  - AI-leader shock -> semi equipment: -0.52 (t -2.33);
  - oil shock -> tankers: -0.09;
  - yield spike -> utilities: -0.08.
- The verdicts were written back. The ledger now has **59 rows**, including 7 from this shift: 4 closed
  with verdicts and 3 open.

**The ten open hypotheses the machine wants to test next, by its own EV:**

- EV = power x [P(pos) + (1 - P(pos)) x w_neg] x value x novelty - cost.
- P(pos) is the family's Beta posterior.
- Value is 10 for a return target, 6 for co-movement and 4 for size.

| # | row | EV | why it ranks here |
|---|---|---:|---|
| 1 | H-1270b5a351: vol-managed market for the preservation personality (declared drawdown utility) | 1.82 | Return value 10, negative-informative (w_neg 0.35), P 0.17 |
| 2 | H-81f3e3c259: vol-compression breakout with frictions | 1.28 | Return value; family P 0.20 (no failure yet) |
| 3 | H-4e1d453114: oil shock -> energy up, transports down | 1.16 | Return value 10 x P 0.15; the macro family keeps failing |
| 4 | H-811fe2c09c: generic commodity lead-lag (local 7B) | 1.14 | As #3; a vague row that the value term keeps near the top |
| 5 | H-ae6502fd26: yield spike -> homebuilders | 1.06 | Macro, P 0.13 after 8 rows |
| 6 | H-65079244f4: yield spike -> money-centre banks | 1.05 | As #5 |
| 7 | H-7cd2a074c9: generic rates lead-lag | 1.05 | As #5 |
| 8 | H-039df299c0: oil shock -> refiners and chemicals | 0.92 | As #5 |
| 9 | H-575b8c97c1: regional banks after 2023 (forward log) | 0.84 | Needs forward time |
| 10 | H-3aac7667ef: insider drift via passive execution | 0.78 | Return value, P 0.18; needs a fill log |

**The ranking has a weakness.** The value term (10 for anything aimed at return) dominates a family
posterior that only floors at about 0.13. That is why macro lead-lags stay near the top after five straight
failures. A family P below 0.15 should shrink `expected_power` or the value term. That change is not made
here: it is a ranking-policy decision for the owner.

## 7. Local graphics card: bulk event conversion

- Resumed at 00:46 local with `--minutes 300`. The child process id is recorded locally.
- At the start, 133,411 of 343,126 queue rows were done; the 209,715 left are the "rest" split.
- The final numbers are in the closing addendum.

## WHAT WORKS

- **Decomposing a comparison before believing it.** One table turned 106 twin "wins" into 18.
- **Declaring before reading, even for descriptive re-scores.** The re-score's validation line for qc761 was
  not treated as a validation read, because it was not declared as one.
- **The ledger's loop.** It generates, dedupes, declares, runs and writes back unattended, for $0.003.

## WHAT DOES NOT

- **"Beats its matched twin" on the turnover-scaled board, as evidence of anything.** Use pure selection
  (gross vs gross) or the fair twin instead.
- **Shorting the comparison leg of small-cap relative edges.** Borrow plus spread exceeds the edge.
- **Volatility forecasting as a route to better book-level log utility**, including with earnings
  seasonality.
- **Insider clusters net of the spread**, at any horizon and in any era.

## HIGHEST-EV EXPERIMENT

**Stop searching for new rules. Fix the benchmark code:**

1. In `library_on_crsp` / `bridges_on_crsp_run`, replace the twin's full-round-trip charge with the twin
   basket's own turnover (the fair twin).
2. Re-issue the board's verdicts. Tonight's CSV already holds the numbers.
3. Put **pure selection** and **net - market** on every receipt.

This is an integrator change to shared code (not made here). It costs $0 and about 1 hour. It removes the
single largest source of false "relative edge" claims this programme has produced.

## CONTINUE FROM HERE

```powershell
$env:AEGIS_PERSONAL_MODE="0"
.venv\Scripts\python.exe -m scripts.hyp_investable --part declare --tag <NEW>   # then --part inputs, decompose, run
.venv\Scripts\python.exe -m scripts.hyp_twin_board --run-id <NEW>               # ~45 min, resumable
.venv\Scripts\python.exe -m scripts.hyp_restatement --part declare --tag <NEW>  # then --part run
.venv\Scripts\python.exe -m scripts.hyp_volmanaged --part declare --tag <NEW>   # then --part run
.venv\Scripts\python.exe -m scripts.hyp_insider_events --part declare --tag <NEW>   # then run / declare_lowcost / run_lowcost
Remove-Item backend\data\optimus\hyp_lab\STOP     # only with the owner's go: arms the 09:30 ledger nightly
ft_lab\.venv\Scripts\python.exe -m ft_lab.bulk_events --minutes 80   # resumable; stop with ft_lab\runs\STOP
$env:AEGIS_IGNORE_DOTENV="1"; .venv\Scripts\python.exe -m pytest backend/tests/test_hyp_investable.py -q -p no:cacheprovider
nn_lab\.venv\Scripts\python.exe -m pytest nn_lab/tests/test_fetch_assets.py -q -p no:cacheprovider
```
