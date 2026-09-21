# 2026-09-21 — Monday: rank → return calibration, and the first per-name μ

- **Chunk 22 — the map from a signal's DECILE to a RETURN MAGNITUDE, BUILT**
  (`scripts/calibrate_signal_return.py` = the night job `C7_signal_calibration`,
  stage `features`, box 60 min, resumable per signal; `backend/services/signal_calibration.py`
  the reader; `roi_rank` + `decision_authority` the two consumers; 37 new tests,
  no model, no network, nothing outside `tmp_path`). Murat's review of 09-20,
  issue 1: *"expected return comes from the leading signal FAMILY's average;
  downside from the ticker's vol — so among names sharing a family the rule
  prefers the lowest-vol name."* Both halves are answered: `mu_i` is now the
  candidate's **own score decile's** mean (net of that decile's own turnover
  cost) and the downside is that decile's **measured 20th percentile**, with
  the vol path kept as a printed fallback. The family it calibrates is
  DERIVED (`recommendation._ADAPTERS` × the registry's PICKER permission),
  never listed — exactly three signals can lead.

- **The first real run (41.5 s, $0.00, 2006-2024, first test year 2009, 191
  month blocks, 12 Holm tests) graded all three WEAK. EXPLOIT stays empty, and
  now it can only become non-empty through measurement.**

  | signal | verdict | D10−D1 net @21 sessions | NW t | Holm p | blocks | non-empty deciles | Spearman |
  |---|---|---|---|---|---|---|---|
  | `profitability_small` | **WEAK** | **+0.6445 %** (gross +0.6929, cost 0.0484) | +1.588 | 1.000 | 191 | 10 | **0.964** |
  | `insider_opportunistic` | **WEAK** | **−0.0463 %** (gross +0.1248, cost **0.1711**) | −0.348 | 1.000 | 191 | **4** | 0.800 |
  | `fusion_insider_profitability` | **WEAK** | **+0.1306 %** (gross +0.3217, cost 0.1911) | +0.297 | 1.000 | 191 | 10 | 0.927 |

  The closest thing to a positive on the board is `profitability_small` at
  **126 sessions**: net **+5.11 %**, t **2.78**, Holm-adjusted **p 0.065** over
  the twelve-test family — the only cell in the table that comes near the bar,
  and it misses it.

- **Two findings that are about the mechanisms and not about the machinery.**
  (a) `insider_opportunistic`'s edge is **eaten by its own turnover**: gross
  +0.125 %/month against a cost of 0.171 %/month at 25 bps/side on a
  monthly-rebalanced decile. (b) its score is **0.0 for 79.8 % of name-months**
  (no open-market Form 4 in the 90-day lookback), so only **4 of 10** deciles
  are ever populated — "decile 3's μ" does not exist for that signal, and the
  receipt says so instead of printing ten buckets that are really two.
  `profitability_small`'s map is the one that looks like a map:
  D1 −0.417 % → D10 +0.358 % net, monotone at Spearman 0.964.

- **Both nulls behave.** The end-to-end shuffled replication (cut points refit
  on the shuffled training panel) gives gross spreads of +0.084 / −0.029 /
  −0.138 % at |t| < 1 for the three signals; the real gross spread sits at the
  100th / 89.5th / 99.5th percentile of the 200-draw shuffled distribution.
  The null's receipt carries a `read_the_gross` line, because a shuffled decile
  turns over ~100 %/month and its NET is the gross minus a ~1 %/month constant —
  a fact about random rebalancing, not about the shuffle, and it read as a
  t of −4.9 until it was labelled.

- **Today's contract, rebuilt by hand.** 43 rows: **0 EXPLOIT, 1 EXPLORE
  (CVLG), 39 REFUSED**, plus 3 agency BOOK rows. Capital resolution
  **99.75 / 0.00 / 0.25 / 0.00** of $40,000. Worst cases unchanged in kind and
  SMALLER in size: tilt −$100,000 of $1,000,000 (10 × 3 % held to 10 % by
  `IC_TOTAL_TILT_BUDGET`), explore **$100 of $40,000** under the 2 % ceiling,
  additive — against $200 yesterday.

- **What changed capital, and why.** Yesterday INDV held $100 of paper EXPLORE
  on `insider_opportunistic`'s FAMILY row (+0.17 %/month, t 1.40). Today its
  own decile — 9 of `insider_opportunistic` — reads **−0.0726 %/month net**,
  below `EXPLORE_MIN_NET_PCT`, and the position is withdrawn by name. CVLG
  keeps its $100 and its posterior moved from the family row to **decile 10 of
  `profitability_small`: +0.3576 %/month, se 0.1657 from that decile's own
  block-bootstrap CI**, with the t on the row now the signal's own 21-session
  spread t (1.588) instead of the family receipt's rank-IC sentence.

- **The panels, named.** `profitability_small` ← JKP `gp_at` (`wrds/jkp_full/jkp_usa_*.parquet`
  1926-2012 + `wrds/jkp_global_factor_usa.parquet` 2013-2024, `pit_knowledge_column: eom`);
  `insider_opportunistic` ← `sec_insider/insider_events_v1.parquet` (3.13 M rows,
  `observed_at_utc = FILING_DATE_EOD_CONSERVATIVE`, the LIVE formula
  `n_distinct_buyers + tanh($ / $1M)` over the live 90-day lookback);
  `fusion_insider_profitability` ← the equal-weight z-composite of the two legs
  on their intersection. Prices: `wrds/crsp_dsf_<year>.parquet` 2006-2024.
  The one construction difference from the live path is printed on the receipt:
  the bulk Form 4 panel excludes 10b5-1 transactions and the live Finnhub feed
  cannot, so the historical score is the cleaner of the two.

## Morning, after Murat's review (Fable)

- `feedback_murat_review_2026-09-21_morning.md` — his forecasting idea (market-structure brief, four roles) and the review, verbatim; roadmap §16 (PROBE, BELIEF_CHANGED, scoped CLOSED, chunks 22c/23a-g).
- `spec_chunk_23a_probe.md` — PROBE as the virtual graded row; refused rows are already graded, what is missing is the label, the hypothesis id, the per-horizon expiry, the reader, and the selection probability.
- `research_sequential_evidence_and_bandits.md`, `research_multi_role_llm_forecasting.md`, `research_precursors_before_the_crowd.md` — the three Sonnet reads of §16.4.
- **N9 measured locally, $0, 581 s:** `N9_candidate_measure_run01.json` — 11,386 candidates on disk (every DeepSeek night since 09-19), 3 unevaluable. ORIGIN read: 564 of 8,486 at raw p ≤ 0.05 vs 424 expected, 0 BH survivors. FOREIGN read (parent barred): 1,142 of 10,247 at p ≤ 0.05 vs 512 expected, median excess +0.19%, 0 BH survivors at q 0.10. Twice now the library screens to nothing that survives the family; the excess over chance on the foreign read is the shared "rebound after stressed drawdown" family firing on correlated dates, not 1,142 findings. **Stop buying candidates**: the next DeepSeek dollar goes to a different question.
