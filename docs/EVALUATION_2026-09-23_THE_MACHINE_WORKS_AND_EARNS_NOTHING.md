# Evaluation, 2026-09-23 — the machine works and it earns nothing

Written after stopping everything at Murat's request, from receipts rather than
recollection.

---

## RESULTS SCOREBOARD

| line | state |
|---|---|
| best historical net strategy vs market | **none** — §59 closed price/volume; nothing has replaced it |
| best forward paper strategy | fleet **$461,940 of $500,000, −7.6%**; last session **−0.19% vs SPY −0.09%** |
| independent selector count | still 1 (the stale funnel) + 1 measured-negative ranker |
| farm candidates tested / promoted | 4 rankers × 7 book sizes, **0 promoted** |
| new actionable finding | fundamentals carry **39 bps/month**; the panel ends 2024-12-31 |
| external execution drag | **not measured** — no PC fill has ever happened |
| LLM spend | **$0.00** |

> ## RESULT IMPROVEMENT: NONE.
>
> Twelve hours, 144 cycles, zero errors, and PC-PAPER is exactly
> **$1,000,000.00 with 0 positions**. Not one decision changed capital.

---

## 1. What the night actually did

| | |
|---|---|
| cycles | **144**, resumed once at cycle 19 |
| unit failures | **0** across reconcile / rank / grade / learn |
| skipped units | 225 (the bars fingerprint working as designed) |
| slow cycles (>120s) | **0** |
| NAV rows with a benchmark | **144** |
| orders | **0** |

Market over the session: **SPY −0.09%, QQQ +0.76%, IWM +0.55%.** Murat's read
("yesterday was very positive so today might go back a bit") was right on SPY
and wrong on the other two — large caps gave a little back while the rest rose.

The ranking it held, and refused to act on:

    2,929 names, asof 2026-09-21
    IC +0.0162 (t +5.30)         <- a real, stable ordering
    top-20 OOS net -1.09%/21d    <- and it loses money

That pair of numbers is the whole problem in two lines. The ordering carries
signal; the tradeable end of it does not survive costs.

## 2. The honest verdict on the session

**The infrastructure is now good.** It genuinely is, and the evidence is
specific rather than hopeful:

* a stop request landed **inside** the rank unit twice and lost nothing;
* a **live 12-hour run was patched at cycle 19 and resumed** from its
  checkpoint — which is the feature doing exactly the job it was built for;
* memory went **7,835 MB → 427 MB** once the heavy units moved out of process;
* 144 cycles, 0 errors.

**And it earned nothing.** PC-PAPER has never placed an order. The five Railway
books that DO trade are down 7.6% and underperformed again on a flat day.

The two facts are not in tension. The machine is excellent at running,
checkpointing, reporting and refusing — and what it refuses is correct, because
there is nothing worth trading. **A perfect executor of an empty decision is
still empty.**

### Where the session's hours went

Roughly: infrastructure and safety ~60%, research ~25%, and ~15% on OpenClaw
browser-profile wrangling plus recovering from the WhatsApp incident. The last
bucket produced no movement on money at all and was largely self-inflicted.

## 3. The causal chain, stated once

    the loop cannot trade
      <- because the ranker is MEASURED_NEGATIVE
      <- because price/volume carries +0.28% gross against a 35 bps toll (§59)
      <- and the one input with real amplitude (fundamentals, 39 bps/month)
         has a panel that ends 2024-12-31

Every link is measured. The chain terminates in a **data** problem, not a model
problem, and that is the good news: the last link was closed yesterday and
never connected.

`scripts/pull_sec_fundamentals` works — 10,459 tickers mapped, `gp_at`
computable for 88% of a test set, filings through 2026-09-10, PIT-correct on
`filed`. **It has never been joined to the ranker.** That join is the entire
remaining distance between "the machine runs" and "the machine has an opinion
worth funding."

## 4. What to do, in order

### P0 — join fundamentals to the ranker and re-run the bake-off

The one experiment that can flip `MEASURED_NEGATIVE`. Everything else is
downstream of its answer.

1. Pull SEC facts for the ~2,900 ranked names (~12 min at the current rate).
2. Join to the price panel on **ticker + `filed` ≤ decision date**. Never on
   `end` — that is how a backtest trades on information it did not have.
3. Add `gp_at`, `ope_be`, `be_me`, `at_gr1` as features.
4. Re-run `night_rank_bakeoff --survivorship-free` with the breadth sweep.

**Pre-register the read now, before the numbers exist:** the challenger must
beat the incumbent's worst breadth cell net of costs, at **every** k from 20 to
300, over ≥ 60 month-blocks. A win at one k is the maximum of 28 cells and
means nothing (that lesson cost a day already). If it fails, fundamentals are
closed at this horizon on our universe and the next input is news/revisions.

Coverage is the risk worth pricing in advance: JPM produced **nothing** because
banks file neither `CostOfRevenue` nor `OperatingIncomeLoss`. If financials and
REITs drop out, the surviving universe is a sector bet, and the bake-off must
report coverage by sector before anyone reads its return.

### P1 — decide the funnel's fate

`funnel_night10.json` has been serving August since 11 August and still feeds
every EXPLOIT / EXPLORE / PROBE row. Either give it a scheduled caller or
retire it and let the ranker be the selector. **Leaving a 43-day-old file
wired into the decision path is the defect that started this whole session**,
and it is still wired in.

### P2 — measure the fleet's underperformance properly

Two sessions of evidence, both negative:

| date | fleet | SPY | gap |
|---|---:|---:|---:|
| 2026-09-21 | +0.60% | +1.55% | **−0.95 pp** |
| 2026-09-22 | −0.19% | −0.09% | **−0.10 pp** |

Two points is not a result. Alpaca's portfolio-history endpoint carries a daily
equity series per book, and SPY over the same dates is already on disk — so a
proper daily relative series, with a beta estimate, is an afternoon's work and
would say whether this is **negative alpha** or **high beta in a flat tape**.
Those two diagnoses have opposite fixes, and right now nobody knows which it is.

### P3 — the collector, pointed at the gap

`openclaw_collector` writes typed events and nothing consumes them. Point it at
company IR pages for the **unstructured** half (guidance language, management
wording changes) once P0 says whether the structured half pays. Not before —
building a second data pipeline before the first is graded is how the last six
weeks went.

## 5. What NOT to do next

* **Do not add a model.** Four rankers were tested; the best clears its own
  costs at no book size. A fifth on the same inputs is the same answer.
* **Do not lower the trade gate.** `MEASURED_NEGATIVE` is not timidity — it is
  a top-20 book that lost money over 122 month-blocks and 3,578 names. Trading
  it to "get data" would buy known-negative expectancy with real paper capital
  and teach the learner that losing is normal.
* **Do not build more infrastructure.** It is the part that works.

## 6. Open items owed to a human

| item | who |
|---|---|
| WhatsApp → Linked Devices → log out the OpenClaw device | Murat |
| `/revoke` the Telegram token (it was pasted in a chat log) | Murat |
| Decide: regenerate the funnel, or retire it | Murat |
| 3 pre-existing suite reds (E2 float tolerance, X2 receipt protocol) | next session |
| 2,911 forecasts stranded on 105 tickers outside the price panel | next session |
