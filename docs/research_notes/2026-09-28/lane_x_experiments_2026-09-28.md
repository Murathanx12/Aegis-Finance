# LANE X experiments, 2026-09-28: Kronos, a blinded LLM check, and the LEAN scoping

Licence: `PRODUCT_EXPERIMENT` (no claim). One variant each, no tuning, and a stop declared in code
before the run. Roadmap: `docs/ROADMAP_2026-09-28_MEASURE_BEFORE_YOU_ADD.md` LANE X.

## RESULTS SCOREBOARD

| item | question | deciding numbers (post-cutoff only) | verdict |
|---|---|---|---|
| X1 Kronos-small, zero-shot | 21-session vol vs the trailing-63 prior; top-20 by forecast return vs the panel's random portfolio | QLIKE **0.746 vs prior 0.415**, worse on **26 of 26** dates (diff +0.331, t +12.9); vol rank corr **0.48 vs 0.75**; long top-20 minus random **+0.06%/mo, SE 0.98, t 0.07, MDE 2.7%** | **FAILED_VARIANT** |
| X2 DeepSeek, NAMED vs BLINDED | 5-session direction and range, 40 names x 12 weekly dates after the measured cutoff | hit **48.8% [44.3, 53.2]** NAMED, **47.9% [43.5, 52.4]** BLINDED; ranges lose to the trailing sd (QLIKE +0.19 / +0.31, t +2.4 / +3.3) | **FAILED_VARIANT** (both arms) |
| X2 leakage (famous pre-cutoff moves) | does the name or date change the answer? | NAMED - BLINDED hit **+23.3 pp, SE 9.2** row-paired, but 6 of the 8 net flips sit on two April-2025 dates | **CANNOT_DISTINGUISH** |
| X3 LEAN replication | a second engine for the finalists | gate "a rule survives M1" not met: all four M1 leads are **CANNOT_DISTINGUISH** | stays `DEPRIORITIZED`; nothing installed |

New actionable finding: none. RESULT IMPROVEMENT: NONE. LLM spend for the whole of X2: **$0.05 by the
provider's balance** ($33.51 → $33.46, cent resolution); $0.073 priced at the served model's row.
This continuation spent $0.00.

## X1: Kronos zero-shot on our survivorship-free panel

Receipt: `backend/data/optimus/experiments_2026-09-28/x1_kronos_20260928_post_receipt.json`
(rows `x1_kronos_20260928_post_rows.jsonl`, 7,800 rows, sha256 in the receipt). Script
`scripts/exp_kronos_2026_09_28.py`, model `NeoQuasar/Kronos-small` + `Kronos-Tokenizer-base`,
repo commit `67b630e6`.

**State found.** The detached run had finished all 26 post-cutoff dates (2024-06-28 → 2026-07-31,
300 names each, ~250 s/date), then died in the ANALYSIS step: pandas' `method="spearman"` imports
scipy lazily, and `.venv_kronos` has none. No row was lost or recomputed. Fix: a scipy-free
`spearman()` (pairwise NaN drop, average ranks, Pearson), pinned against pandas by a test. The
receipt produced before and after the change agrees to 5.6e-17 on every per-date value, and the
analysis now also runs inside `.venv_kronos`.

**Construction.** Month-end decision dates. Each date takes a deterministic draw of 300 names from
those traded on t with ≥400 sessions, 63-session median dollar volume ≥ $20M and close ≥ $5
(`prices_deep` bars + delisted bars). Each name gets 400 sessions of OHLCV context and 8 sampled
21-session paths, at T=1.0 and top-p 0.9. Future timestamps come from the business-day calendar, not
from realised sessions. Costs are the library's band round trip per name per leg (6/10/18/35 bps).
The random portfolio is the equal weight of the 300-name sample minus its mean round trip (the
expectation of a random-20).

**Contamination.** Kronos' pretraining data "extends up to June 2024" (arXiv:2508.02739; this is
the authors' statement, and we cannot inspect the published weights' training set). Every hold month
here is **2024-07 … 2026-08, all after that cutoff**. No contaminated dates were run (the PRE block
has `n_dates: 0`), so no contaminated number exists to be confused with the verdict.

**Volatility (versus the trailing 63-session sd).**

| | Kronos | prior | diff (K - prior) |
|---|---|---|---|
| QLIKE, mean of 26 dates | 0.746 | 0.415 | **+0.331**, SE 0.026, t +12.9, worse on 26/26 |
| by hold year 2024 / 2025 / 2026 | | | +0.47 / +0.26 / +0.33 |
| leave-one-year-out worst / without best 5 | | | +0.29 / +0.29 |
| Spearman with realised sd | 0.483 | 0.746 | **-0.262**, t -13.0, worse on 26/26 |

Kronos' forecast sd runs at 1.24x the realised sd (median ratio). Recalibrating the scale would not
rescue it, because the rank correlation is scale-free and loses on every date. The stop rule forbids
the attempt in any case.

**Ranking (21-session hold, net of band costs, monthly, keyed by HOLD month).**

| series (26 hold months) | mean | SE | t | MDE 80% | 2024 / 2025 / 2026 | LOYO worst | w/o best 5 |
|---|---|---|---|---|---|---|---|
| Kronos long top-20 net | +1.27% | 1.25 | 1.02 | 3.5 | +0.34 / +0.12 / +3.69 | +0.20 | -1.02 |
| random portfolio net | +1.21% | 0.88 | 1.38 | 2.5 | +1.33 / +0.97 / +1.47 | +1.09 | -0.21 |
| **Kronos long - random** | **+0.06%** | 0.98 | **0.07** | 2.7 | -0.98 / -0.85 / +2.23 | -0.90 | -1.79 |
| 12-1 momentum long - random | +0.08% | 1.47 | 0.06 | 4.1 | +1.58 / -0.68 / +0.09 | -0.37 | -2.10 |
| Kronos long - momentum long | -0.02% | 1.94 | -0.01 | 5.4 | | | |
| Kronos L/S top-bottom 20 net | +1.07% | 2.00 | 0.54 | 5.6 | -1.16 / -1.16 / +6.09 | -1.16 | -2.66 |
| return IC (Spearman), Kronos / momentum | -0.002 / -0.025 | | -0.08 / -0.73 | | | | |

The Kronos ranking line comes from 2026 alone: its hold-year mean there is +2.2 pp over random, and
it is negative in 2024 and 2025. It also turns negative without its best five months, which is
protocol item 11 in a single row. 12-1 momentum does no better on the same names, which matches the
2026-09-22 prior (§59: price and volume cannot rank at 21 sessions after costs).

**Verdict: `FAILED_VARIANT`.** The declared rule (post-cutoff dates only): VOL beats the prior if
the QLIKE diff is < 0 with t ≤ -2, and RANK beats random if long-minus-random is > 0 with t ≥ 2.
Neither is met. No second variant, no tuning.

What it can say: at 26 monthly blocks it rules out a volatility forecast as good as the naive prior
(the gap is 13 SE). It cannot see a ranking edge smaller than ~2.7%/month over random. What it cannot
say: anything about Kronos-base or Kronos-large, fine-tuning, intraday horizons, or other universes.

## X2: the blinded LLM check (the StockBench idea, run on our stack)

Receipt: `backend/data/optimus/experiments_2026-09-28/x2_blind_20260928_receipt.json`
(rows `x2_blind_20260928_rows.jsonl`, calls `…_calls.jsonl`, balance `…_balance.jsonl`,
probe `…_probe.json`). Script `scripts/exp_llm_blind_gap_2026_09_28.py`.

**Arithmetic verified from the rows.** Every number below was recomputed independently in this
session and matches the receipt. There are 1,020 rows, the parse rate is 1.00, and **every row and
all 128 logged calls were served by `deepseek-flash`** (the request was for `deepseek-chat`), with 0
call errors. The price probe measured the cutoff at **2025-12**, while the model's self-report says
"early 2025". The post window is 2026-07-02 … 2026-09-18, seven months or more beyond it.

| set / arm | n | hit | Wilson 95% | always-up hit | date-block t (12 or 15 dates) | QLIKE vs trailing sd (SE) | 80% range coverage | mean conf / Brier (coin 0.25) |
|---|---|---|---|---|---|---|---|---|
| post / NAMED | 480 | 48.8% | 44.3-53.2 | 46.7% | -0.39 | +0.185 (0.077), worse | 67.7% | 0.568 / 0.256 |
| post / BLINDED | 480 | 47.9% | 43.5-52.4 | 46.7% | -0.67 | +0.306 (0.093), worse | 64.4% | 0.573 / 0.259 |
| famous / NAMED | 30 | 53.3% | 36.1-69.8 | 63.3% | +0.52 | +11.1 (2.1), worse | 0.0% | 0.559 / 0.254 |
| famous / BLINDED | 30 | 30.0% | 16.7-47.9 | 63.3% | -0.18 | +14.0 (2.7), worse | 0.0% | 0.571 / 0.282 |

- **Direction.** No arm beats a coin, and both post arms sit within 2 pp of always-up. The
  date-block MDE is ~9 pp, so the experiment excludes a hit rate above ~53% at 95%, but it cannot
  see an edge of 1-8 pp.
- **Magnitude.** The model's 80% ranges are 0.68-0.70x the trailing sd and cover 64-68% of
  outcomes. QLIKE loses to the trailing-volatility prior in both post arms (t +2.4 and +3.3). The
  rank correlation of range width with |return| ties the prior when the names are shown (0.41 vs
  0.41) and trails it when they are blinded (0.36).
- **Calibration.** Confidence clusters at 0.55-0.61 and carries no information: the 0.6-0.7 bin
  hit 44.6% blinded and 56.0% named. Brier is worse than the base rate (0.249) in every arm.
- **Leakage.** On post dates the arms agree on 87% of directions and the gap is +0.8 pp (SE 1.6,
  date-block t 0.54). Blinding changes nothing where there is nothing to remember. On the 30
  famous pre-cutoff moves they agree on 70%. Of the 9 discordant pairs the NAMED arm is right on 8,
  and 6 of those 8 fall on 2025-04-04 and 2025-04-17, the tariff-crash rebound. With real dates,
  the named arm called up; seeing only a drawdown, the blinded arm called down. That pattern fits
  a model that remembers the **regime by its date**, not individual stock outcomes. The named 80%
  ranges covered **0 of 30** famous moves and confidence never went above 0.60, so no magnitude was
  memorised. With effectively 3-4 independent date clusters, this is **CANNOT_DISTINGUISH**, not a
  measured leak.

**Verdicts.** The declared rule on the post arms: DIR needs a Wilson low > 0.5 and a date-block
t ≥ 2; VOL needs a QLIKE diff < 0 with t ≤ -2; the arm is FAILED_VARIANT if neither holds and the
Wilson high is < 0.55.

- post/BLINDED: `FAILED_VARIANT` (from the receipt).
- post/NAMED: `FAILED_VARIANT`, applying the same rule here (Wilson high 0.532, QLIKE worse at
  t +2.4).
- Leakage: `CANNOT_DISTINGUISH`.

What it cannot say: anything about a sequential agent with memory (StockBench's actual design),
about other models, or about horizons beyond 5 sessions. It asks one question: handed a PIT packet,
does this model know the next week?

**Spend.** Balance $33.51 → $33.46 = **$0.05** across probe, first and run (cent resolution). The
ledger, priced at the served row, shows $0.073 over 134 calls. The cap was $1.50; ~$1.43 is unspent
and not needed.

## X3: LEAN replication, scoping only (nothing installed)

The design already exists in `docs/research_notes/2026-09-26/research_library_expansion_and_lean.md`
§2.5. It is a `PythonData` adapter that replays `strategy_library/top10_for_replication_<run>.json`
(held symbols by date, band costs, monthly return series) through QuantConnect LEAN, which is
Apache-2.0 and runs from a local CLI. `outside_methods_compared_2026-09-28.md` §1.2 costs it at
2-4 days.

- **Value:** architectural independence. A second, event-driven engine can catch bugs that a
  vectorised engine cannot see in itself (fills, corporate actions, rebalance timing).
- **Costs:** our own bars reformatted into LEAN's layout, a C#/.NET core to maintain, and a
  statistics layer with a bug history (PR #3979, issue #6810). Its report would be spot-checked,
  never trusted.

**Gate.** The roadmap holds X3 at `DEPRIORITIZED` until a rule survives M1. M1 ran today
(`lane_m_build_2026-09-28.md`): `mom_12_1_q`, `disp_short_avoid`,
`qc470_mom252_quarterly_riskparity` and `mom_12_1_q_trend` are all `CANNOT_DISTINGUISH`. No offset
loses, and none survives. Replicating a rule that has not survived its own calendar test would only
verify the engine's arithmetic on a result nobody should act on. **X3 stays DEPRIORITIZED.**

If a rule does survive M1, the first cell is `mom_12_1_q` alone, on one calendar. Its net cumulative
and monthly series must match the library receipt to within 0.1%/month before any other finalist is
run. A mismatch is a finding about one of the two engines, and it is traced before any number is
quoted.

## Three sentences

**WHAT WORKS:** the stop rules. Two outside methods, a price foundation model and our own LLM, were
each measured on post-cutoff dates against the dumbest honest baseline and closed in an afternoon
for $0.05, with the verdict declared in code before the run.

**WHAT DOES NOT:** Kronos (QLIKE worse than the trailing-63 sd on 26 of 26 dates; ranking +0.06%/month
over random, t 0.07) and DeepSeek (48% direction; ranges narrower than, and worse than, the trailing sd)
both fail to beat the priors they would replace.

**HIGHEST-EV EXPERIMENT:** the forward read of TRIAL-LIB-FWD-TWIN-1 on 2026-10-26, the frozen
library bets against their matched twins on dates nobody has seen. Every backward-looking route
tested today, including two from outside, has ended at the prior.
