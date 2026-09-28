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

> **Annotation 2026-09-28 (lane M4c): the comparator the pitch leaves out, printed beside it.**
> On the same kind of question -- "will |move| exceed the threshold" -- a free formula,
> p = 2(1 - Phi(thr / (sigma_63 * sqrt(h)))), scores **+10.0% held-out Brier skill at h = 1 against
> +5.5% for the LLM arms** (+5.7% for the LLM on the prior's own rows), and wins 7 of 8 held-out
> days; at h = 5 it is **+5.9% vs +2.6%** (6 of 8 days). Receipt:
> `backend/data/optimus/learning_reports/report_2026-09-27.json` -> `closing.vol_prior` (committed
> version generated 2026-09-27T00:03:08Z; identical values in the 23:58:55Z regeneration; 1,560 rows, 775 held out, 2026-08-24 -> 2026-08-27, all LLM arms pooled,
> climatology = the training half's base rate). So on magnitude, the process's skill is below a
> formula that costs nothing, and the pitch's "discipline matters more than model choice" must be
> read beside that. Two further cautions: (1) +8.97% is the investigator's RECALIBRATED held-out
> skill (raw +4.38%), while -27.98% is the personas' RAW skill (recalibrated -0.00%); like for like
> it is raw +4.38% vs -27.98%, or recalibrated +8.97% vs -0.00%. (2) **+8.97% is UNVERIFIED against
> its named receipt**: `NEGATIVE_RESULTS.md` §64 names `specialists/scoreboard_2026-09-24.json`,
> and neither committed version of that file (`7b0d49d2`, `89bc65af`) nor the file on disk carries
> the held-out split or 0.0897 -- it carries full-sample per-arm skill only (investigator arms
> +3.7% to +8.0%). The number lives in the commit message of `7b0d49d2` and in
> `HANDOFF_2026-09-24_THE_LEDGER_WAS_THE_ANSWER.md`. The adversarial review's "+10.2% vs +5.7%"
> (`ADJUDICATION_2026-09-26_WAVE1.md` row 3) could not be matched to a receipt; the receipt above
> says +10.0%.

> **WITHDRAWN 2026-09-28 (lane M review F7): the sentence "a structured evidence-gathering
> *process* beats persona-styled LLM prompting by a wide margin out of sample (+8.97% vs −27.98%
> held-out skill)" in the pitch above.** The text is kept visible; it is no longer claimed. Why:
> (1) it sets a RECALIBRATED figure (+8.97%) against a RAW one (−27.98%); like for like the gap is
> raw +4.38% vs −27.98% or recalibrated +8.97% vs −0.00%; (2) its named receipt,
> `backend/data/optimus/specialists/scoreboard_2026-09-24.json`, does not contain 0.0897 or a
> held-out split (checked 2026-09-28 by a literal search of the file on disk; the committed
> versions `7b0d49d2` / `89bc65af` were checked by the M4c annotation above). It is withdrawn until a
> committed receipt reproduces it. **No process-vs-persona claim belongs in this pitch on the
> present evidence.**
>
> **What the receipts DO support** (all from
> `backend/data/optimus/learning_reports/report_2026-09-27.json` -> `closing.vol_prior`, committed
> in `6a7a2465`; values checked identical in HEAD and on disk 2026-09-28; ONE held-out window of 4
> calendar days, 2026-08-24 -> 2026-08-27, 775 held-out rows of 1,560; all LLM arms POOLED, arm
> `*`, not the investigator alone; question: will |move| exceed the threshold):
>
> - At **h = 1 session**, the free trailing-volatility formula scores **+10.0%** Brier skill vs
>   **+5.5%** for the LLM arms (+5.7% for the LLM on the formula's own rows) and wins 7 of 8 days.
>   VERIFIED. Correction to the brief that asked for this: the receipt's horizon is **1 session,
>   not 21**, and the comparator is **all LLM arms pooled, not the investigator**; no receipt was
>   found for an investigator-only or a 21-session version of this comparison (looked in
>   `learning_reports/report_2026-09-27.json` `closing.vol_prior`, which carries horizons 1 and 5
>   only). The 21-session / investigator form is UNVERIFIED.
> - At **h = 5 sessions**, like for like (the LLM on the formula's own rows) the **LLM leads:
>   +7.5% vs +5.9%** (`skill_llm_own_prior` 0.0747 vs `skill_prior` 0.0592). VERIFIED. On all
>   rows pooled the LLM is +2.6%, and the receipt's `winner` field says `prior` (6 of 8 days),
>   because it compares the pooled LLM figure; both readings are printed here.
>
> The sentence the pitch can carry: "On one held-out week of August, a free volatility formula
> forecast the SIZE of next-day moves better than our LLM arms (+10.0% vs +5.7% Brier skill, like
> for like); at 5 days the LLM was ahead like for like (+7.5% vs +5.9%). Our earlier +8.97% vs
> −27.98% comparison mixed a recalibrated number with a raw one and is withdrawn until a committed
> receipt reproduces it."

Of ~21 products surveyed, none publishes independently audited, cost-inclusive
forward evidence vs SPY; only Danelfin and Numerai grade their own calls at all.

## 9. Value proposition, ranked (from `research_notes/2026-09-26/research_value_proposition_and_competitor_ranking.md`)
Two personas, 21 competitors, ten criteria scored 0-3 with a source each:
- **P2 — the sophisticated investor who wants a machine to beat SPY hands-off:**
  Aegis leads on paper (12) over Danelfin (11) and Numerai (9); on the one
  criterion P2 pays for — forward, cost-inclusive evidence vs SPY — Aegis
  scores 1/3, level with Numerai, below Danelfin. The 39 priced paper accounts
  at −1.12% are the honest number.

> **Correction 2026-09-28 (lane M4a; nothing above is erased).** "39 priced" is the BROKER-INCLUDED scope: website lanes, night books and twins, murat_book, the five legacy Alpaca accounts and PC-PAPER. It was NOT superseded by `3204eb4d`: that commit's `roi_2026-09-27.json` (generated 2026-09-27T06:44:32Z) still prints 39 priced, 7 ahead of SPY, 32 behind, -1.315%; the 09-26 broker-included receipt (`b137fff7`, 03:57:21Z) printed 39 / 7 / 32 / -1.124%. The "33 priced, 6 ahead, 27 behind, -0.27%" quoted on 2026-09-28 is the scheduled `--no-broker` pass (generated 2026-09-27T23:51:21Z), which overwrote the same file name and leaves out the six priced broker accounts (hack1/2/4/5/6 at -1.2% to -20.0%, PC-PAPER -0.2%): a narrower scope that flatters the aggregate, not a correction. **Current, broker-included, read-only:** 39 priced, 7 ahead of SPY, 32 behind, aggregate **-1.34%** (`backend/data/optimus/paper_accounts/roi_2026-09-28T060842Z.json`, generated 2026-09-28T06:08:42Z; hack3 BROKER_ERROR HTTP 401, never $0). Scope and receipt: `docs/research_notes/2026-09-28/lane_m_build_2026-09-28.md` §M4.

- **P1 — the person who does not know how to invest:** Betterment/Wealthfront
  lead; Aegis ties on substance and scores **0 on accessibility** — no novice
  product exists yet.
- **Revenue:** the SEC and the SFC draw the same line — an impersonal,
  transparent screen/ledger is not advice; output tailored to one user's
  supplied information is (RIA / Type 4/9). Comparable pricing: Danelfin
  $29–179/mo, Composer $30/mo as an RIA, robo-advisors 0.25%. Our cost to
  serve is a broadcast cost (~$0.05 per card, ~$0.30 per 100 names per day,
  ~$50/mo Railway), near-zero marginal per subscriber — contingent on a
  first paying user, of which there are none.
- **Positioning, one sentence each:**
  - P1: *"Aegis writes down what it believes about the market every day,
    grades itself against what actually happens, and shows you both — for
    free, in plain language, before it ever asks you for a dollar."*
  - P2: *"Aegis is the only system we found that freezes every forecast
    before the outcome and grades it against reality at scale — the
    discipline a real edge would need to prove itself is built and running;
    the edge itself is not proven yet, and we say so."*
