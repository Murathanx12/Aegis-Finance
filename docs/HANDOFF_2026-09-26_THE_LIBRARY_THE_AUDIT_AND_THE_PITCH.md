# Handoff — 2026-09-26 (02:00 → 06:30 HKT) — the strategy library ran, the audit landed, the pitch is provable

Read `AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` (TIER 0) first, then this.
Continues `HANDOFF_2026-09-25_EVENING_THE_MACHINE_FORECASTS_AGAIN.md`.

## RESULTS SCOREBOARD

| line | state |
|---|---|
| best historical net strategy vs market | **none that survives multiplicity.** The library's first night: 112 rules, 336 cells; best DSR **0.293** (bar 0.95), best block-t **2.21** (bar 3.0). Hindsight since 2020: `mom_12_1_q` +49.7% CAGR vs SPY +15.7% — but the best 5 of 115 months carry 38–54% of every winner's log return; without them 12-1 momentum is **+14.6%, below SPY**; random controls +15.0–15.2% ≈ SPY |
| best forward paper strategy | PC-PAPER **$999,143** after its first day (10 PROBE names); 44 books on the clock (v1, v2, reviewer, cards-supports, 20 factory, 12 `lib_` incl. the two green replays) — first grades Monday |
| forecasts | `u_forecast` daily (160-name cap); direction rows now RAW with `shrink_basis` (the 0.65 was magnitude skill); accrual canary green |
| learning | **the learning layer wrote its first 20 rules** (`brain/learned_rules.jsonl`, hindsight-safe, each with n/brier/skill) and its first `policy_state.json` (persona weights 0, reputation weights, PROBE gate 0/21, magnitude +4.1% vs direction −8.7%); DeepSeek fallback when the local model refuses ($0.0005) |
| decisions | the ALLE clash closed: PROBE honours the contract's negative-EV refusals and shares its hypothesis id; PROBE−REFUSED −0.68%/day over 3 blocks stays "not a result" |
| LLM spend, the night | cards $3.20 (09-25) · distillation $0.0005 · forecasts ≤ $2/day cap · library $0 |
| suite / CI | local suite in progress at hand-off; CI green through `13f4edeb`; ~20 commits since await the push |

**RESULT IMPROVEMENT: the sentence Murat asked for exists and is honest —
"this made +1,323% since 2020 when SPY made +162%" prints with DSR 0.293, its
worst year, its worst breadth cell and its best-5-month dependence beside it.
Nothing may be quoted without them.**

## 1. What was built tonight (all committed)
- `strategy_library.py` + `scripts/night_backtest_factory.py` (`7e1b446a`, restored `4e887534`): 112 rules + 4 random controls over the monthly survivorship-free panel (4,793 symbols, 32.8% delist), costs by band, SPY from `learner.benchmark`, checkpoint every 10, STOP file, 90-min box, forward twin books for the DSR top-10 + the two green replays (`forecast_dispersion_v1` +1.02%/mo t 5.65 in replay; Book F seasonality +0.43%/mo t 3.12) that had never run forward. 67 catalogue rows are `NOT_REACHABLE` on this panel (value needs PIT share counts; industry momentum; 13F; options). Ran in **91 s**. Leaderboard: `backend/data/optimus/strategy_library/LEADERBOARD.md`.
- The learn rota (`bbc3730d`): `backtest_factory` and `distil` run once per UTC day out of process; `B_backtest_factory` is also a night job.
- Learning layer (`24c8fb96`): `learner.rule_distillation --ledger`, `policy_state.refresh`, `LEARN_DEGRADED` when nothing is written.
- `u_plan` (`9f8e5e09`): contract refusals exclude PROBE names; `contract_clash` on the receipt; direction forecasts raw with `raw_probability`/`shrink_basis` fields (old rows still parse).
- Tests pinned to their own clocks/fixtures: `test_book_factory` news fixture (UTC), plus yesterday's frozen `iif1_nights`.
- Docs: `AEGIS_STRATEGY_2026-09-26_ONE_PIPELINE.md` (TIER 0), the three research notes (differentiation vs 21 products; 113 strategy seeds; the since-August audit), the audit's adjudication, the PDF source `stock_lists_2026-09-26.md`.

## 2. Delivered to Murat
`C:\Users\mrthn\Downloads\AEGIS_stock_lists_2026-09-26.pdf` (44 pages): the 24
chosen books with theses and falsifiers; the 84 considered cards; the 139-name
potential list with his holdings beside their card verdicts (AARD, BHVN, SLDP,
QUBT against; DKNG neutral); **181 names at ≥100% analyst-implied upside with
≥5 analysts, 365 at 50–100%**, each with the strong-buy/buy/hold mix — under
the §17 warning that target-level upside is a perverse cross-sectional signal.

## 3. The census (what is running, and what nobody was watching)
`scripts.always_on_lab` has run since 09-25 11:55 HKT and spends ~$2.6/day on
IIF1 investigator nights (it wrote `iif1_nights/2026-09-25.json` at 18:32, the
write that turned six laptop tests red). OpenClaw gateway, llama-server (7B,
8k ctx), Optimus MCP ×2, the sim. Keys present and unused: **NVIDIA**
(`integrate.api.nvidia.com`), Polygon, Finnhub, FMP.

## 4. The audit's verdicts that change behaviour (`reviews/ADJUDICATION_2026-09-26_AUDIT_SINCE_AUGUST.md`)
The investigator's skill is magnitude, not direction (−8.7% held out at h=5);
the five arms are ~1.5 independent forecasters; two green replays never ran
forward (now they do); the learning layer had learned nothing (now it writes
rules or a red line); refusals beat probes at 1 day (3 blocks); 14 graded
outcomes nobody reads (chunk 3's panel consumes them); 9 of 14 clashes are
accidents, the ALLE one closed tonight.

## 5. Next (the loop continues)
1. Reviewer on chunk 3b (the library) — attack the DSR null, the best-5-month
   dependence, the adopt/reject rule, and whether momentum's hindsight CAGR is
   the 2020-21 regime wearing ten years' clothes.
2. Chunk 3: the timeline panel (research + schema ready).
3. Chunk 5: the FX leg + dividends before any competition book is graded; the
   `grand_prize` strategy set (10 × 10%).
4. Chunk 6: the source registry — every source's items become forecast rows;
   WSJ is Murat's call; Reddit stays as a graded source, not a trusted one.
5. Murat: register by Oct 5 with the WLS export; an X account; overrule
   anything with a sentence.
