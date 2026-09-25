# AEGIS — the one pipeline (written 2026-09-26 02:40 HKT, after Murat's "we are lacking a clear strategy")

Murat: *"we have so many things, so many independent things that are not
connecting to each other, or the strategies are clashing ... what are we doing
that is different? ... I'm hoping to beat the S&P 500, but we don't have proof
yet ... maximise backtests ... a forward paper account ... if it works we adopt
it ... if Aegis had existed in 2020 to now, this is what it would have done."*

This file is the strategy in one page. Everything else is a lane of it or is
not on it. When a piece of machinery is not on this page it is either a
control, a sensor, or a corpse — and the audit of 2026-09-25
(`research_notes/2026-09-25/audit_services.md`) found most of the 266
services were none of the three: they were built and never joined.

## 1. The sentence

**Aegis is a machine that writes down what it believes before the outcome
exists, grades every belief against reality, and lets only graded beliefs
size capital.** The LLMs read the world; the engine decides; reality grades;
the grades become the weights. Nothing else is the product.

## 2. The pipeline (every box names its live module and its grade)

```
WORLD ──► EVIDENCE ──► FORECAST ──► REPUTATION ──► E[r] ──► BOOK ──► OUTCOME ──► WEIGHTS
 news      typed rows    a row with   per (arm,      one number  frozen,   graded at   refit each
 filings   thesis cards  p, horizon,  observable,    per name,   twinned   1/5/21/63/  night; a
 analysts  revision flow resolves_at  horizon):      decomposed  paper     126 d       weight is
 prices    fundamentals  (25,329 rows) skill, floor 0 by component books    (17,650)    earned
 social*   catalysts     since 08-11   (investigator                (32 live)             only by
                                        +5%, personas 0)                                  outcome
```

| box | live module | its grade today | status |
|---|---|---|---|
| WORLD → EVIDENCE | `news_pull` corpus (75,889 rows, 18 sources), `pull_analyst_targets` (393k revisions), SEC fundamentals + `derive_q4`, `thesis_cards` (84 cards via OpenClaw + DeepSeek), catalyst YAML (31 rows) | evidence has no grade; its FORECASTS do | live |
| EVIDENCE → FORECAST | `u_forecast` (investigator process, h=1/5, 118 rows/day), `u_review` (labels as rows), `thesis_card:v1` rows (166), `review:v0` | investigator family **+4.3% to +6.0%** Brier skill held out; personas **−21% to −70%**, weight 0 | live |
| FORECAST → REPUTATION | `forecast_reputation` keyed `(arm, observable, horizon)` | direction ≠ magnitude enforced (the 0.42 weight was magnitude skill) | live |
| REPUTATION → E[r] | `expected_return` (7 components, Shapley-exact, equal-weight control) | 0 graded blocks → equal weights, flat | live, ungraded |
| E[r] → BOOK | `u_plan`: EXPLOIT (ranker, refused: measured negative) / PROBE (shortlist, 10 × 2%, live since 13:32 ET 09-25) / 32 frozen books with twins (`llm_portfolio`) | first grades Monday | live |
| BOOK → OUTCOME | `u_grade` + `llm_portfolio grade` + `decision_autopsy` over the universe median | PROBE−REFUSED −0.68% at 1 day (6 days) | live |
| OUTCOME → WEIGHTS | `refit` in `u_grade`; PROBE gate keyed to its own 21-session grade; adopt/reject rule in the strategy library (below) | the first refit that moves a weight is weeks away | live |

*social: Reddit read via OpenClaw; X behind a login wall. Murat, 09-26: Reddit
is a bad source. **Decision: no source is trusted by opinion; every source's
items become forecast rows and earn a reliability weight** (`source_registry`
in chunk 6). Candidates to add, ranked by the research due tonight: WSJ (paid;
Murat's call), Yahoo news + analyst pages, SEC 8-K bodies (already in), Google
News RSS (already in), LunarCrush.

## 3. The three claims we can make, and the one we cannot
1. **Every forecast is frozen before its outcome and graded** — 25,329 rows,
   17,650 graded, held-out skill by family. Almost no product does this.
2. **The process beats the persona** — the one positive out-of-sample result
   (§64), and the design rule the whole pipeline now follows.
3. **Every book has a random twin and a sector twin** — a good number must
   beat both before it is a number.
4. **Not yet: beating SPY forward.** The ranker is measured negative; the
   PROBE book is one day old; the 32 books enter Monday. The proof Murat wants
   for the hackathon is what the strategy library (§4) and the era replay are
   for, and it is honest only with by-year, leave-one-year-out and DSR beside
   every headline.

## 4. What the nightly sim is FOR (Murat, 02:00 HKT)
`spec_chunk3b_strategy_library_and_backtest_factory.md` — ≥100 strategies
defined once, backtested the same way every night on the survivorship-free
2016-2026 tape net of costs vs SPY, ranked by DSR with by-year / LOO / worst
cell printed first, the top 10 handed forward paper books with twins, an
adopt/reject rule declared in advance, and (phase 2) the whole pipeline
replayed 2020→now. "This made 1,000% when the S&P made 200%" is printed with
its DSR and its worst year beside it, or not at all.

## 5. What is running on this machine right now (the census Murat asked for)
| process | since | what it does | spends |
|---|---|---|---|
| `scripts.sim_run --session 746074adc086` | 09-26 02:32 HKT | tonight's sim: forecast, review, PROBE plan, grade, learn | ≤ $2/day DeepSeek via OpenClaw |
| `scripts.always_on_lab` (pid 95400) | 09-25 11:55 HKT | the always-on lab: news typing, the 06:30 pass, **IIF1 investigator nights** (wrote `iif1_nights/2026-09-25.json` at 18:32) | ~$2.6/day on INTERNET-INVESTIGATOR-FWD-1 — **this is the service running that nobody was watching** |
| `llama-server` Qwen2.5-7B Q4 (pid 110308) | 09-25 11:59 | local model; 8k context | $0 |
| OpenClaw gateway + supervisor (node, 588 MB) | 09-25 11:54 | browser agent; `muratclaw` profile; 18 denied domains | its DeepSeek spend now lands in the telemetry ledger |
| Optimus MCP ×2, Playwright MCP, Context7 MCP | 09-25 11:55 | Claude Code tooling | $0 |
Keys present: DeepSeek, **NVIDIA (integrate.api.nvidia.com)**, Polygon, Finnhub, FMP. The NVIDIA endpoint is provisioned and unused — a second adjudicator for the DeepSeek-vs-local pairing, to be added to `llm_analyzer` as a named provider, never as "primary".

## 6. Clashes that are experiments, and clashes that are accidents
- **Experiment:** v1 vs v2 (the review's edits, graded); the reviewer's book vs
  the cards-supports book vs the human books; EXPLOIT (refuses) vs PROBE
  (acts) — two arms of `u_plan` graded separately.
- **Accident:** `pm_engine` and `investment_committee.compose_book` still
  compute books nobody grades — retire or wire (audit tonight decides);
  `ESG_CATEGORIES["gambling"]` excludes DKNG while Murat holds it — the basket
  is an IPS constraint, not a view; the ten competition books were built to a
  +50% target with 13-26 names — relabelled rehearsal, rebuilt in chunk 5.

## 7. Lanes, in order (one builder at a time, one reviewer after each)
chunk 3b strategy library (tonight) → chunk 3 timeline panel → chunk 4
future-facing quests (CEO, pivots, politics) → chunk 5 competition engine with
the FX leg → chunk 6 source registry + social → era replay 2020→now.

## 8. The hackathon pitch (from `research_notes/2026-09-26/research_differentiation_and_interdisciplinary.md` §A.4; every sentence provable from receipts)

> "Aegis is not another AI stock-picker chatbot — it is a system where every
> decision is written down and dated *before* the outcome is known, and then
> graded against what actually happened, which almost none of the ~20
> 'AI-investing' products we surveyed do at all. Our one measured result so far
> is that a structured evidence-gathering *process* beats persona-styled LLM
> prompting by a wide margin out of sample (+8.97% vs −27.98% held-out skill),
> which is evidence that discipline matters more than model choice. What we
> cannot yet say — and won't claim until we can show the receipt, not a
> backtest — is that this beats the S&P 500 forward, net of costs; that test is
> running now, live, in paper accounts, and the honest answer today is 'best
> historical net strategy vs market: none.'"

Of ~21 products surveyed, none publishes independently audited, cost-inclusive
forward evidence vs SPY; only Danelfin and Numerai grade their own calls at all.
