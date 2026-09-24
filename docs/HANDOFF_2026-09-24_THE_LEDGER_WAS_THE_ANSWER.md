# Handoff — 2026-09-24. The evidence was already bought; nobody had read it.

Continuation file for the next session. Read this, then `docs/RESEARCH_QUEUE.md`.

---

## RESULTS SCOREBOARD

| line | state |
|---|---|
| best historical net strategy vs market | **none.** §59/§60/§61/§63 all closed |
| best forward paper strategy | fleet **$450,994 / $500,000, −9.8%**; PC-PAPER flat at $1,000,000 (refuses to trade a measured-negative ranker) |
| **new actionable finding** | **§64 — the `investigator` process forecasts at +8.97% Brier skill out of sample; nine thematic LLM specialists score −27.98% and their optimal weight is ZERO** |
| second finding | **§62's mechanism measured**: a stopped position recovers +0.93% to +1.19%, at every level, in every year |
| independent selector count | unchanged |
| LLM spend this session | **$0.00 on research**; two OpenClaw quests on `deepseek-flash` |

**RESULT IMPROVEMENT: the first positive out-of-sample forward result in the
programme — and it is about method, not about markets.**

---

## 1. What moved, in order of how much it matters

### §64 — fourteen LLM specialists, 14,703 graded forecasts

`predictions.jsonl` had been accruing since 2026-08-11 and **had never been
read**. Every row was frozen before its outcome existed, so it is forward
evidence, not a backtest.

    overall Brier        0.2625
    climatology          0.2244   (always predict the base rate)
    SKILL              -17.01%
    calibration gap    +17.0pp    every specialist says more than happens

Then the split, held out (first half by date fits, second half scores):

| family | n test | raw skill | recalibrated | weight | discrimination |
|---|---:|---:|---:|---:|---:|
| `investigator:*` (structured evidence) | 2,325 | **+4.38%** | **+8.97%** | 0.65 | **+16.7** |
| thematic personas (9 arms) | 5,027 | **−27.98%** | −0.00% | **0.00** | −2.0 |

Skill lives at **h=1** (+5.75%, disc +17.8) and is gone by h=5 (+0.09%).

**A structured evidence procedure forecasts. A persona does not.** Murat reached
the same conclusion from the other side the same day — "a microscope, not a
fortune teller". This is that, measured.

**Do next:** turn the nine thematic specialists off (a spending decision), apply
the 0.65 shrink to investigator output, ask at h=1. `Q-3` in the queue.

### §63 — the SanDisk archetype: detector built, refuted as a score

Built `backend/services/inflection.py` off one case and its matched control:

| SanDisk (filed) | rev | QoQ | gross margin |
|---|---:|---:|---:|
| 2025-05-12 | $1.70B | −9.7% | 22.5% |
| **2025-11-07** | $2.31B | **+21.4%** | +3.6pp — price was **$239** |
| 2026-05-01 | $5.95B | +96.7% | +27.4pp — price **$1,187** |

Western Digital over the same window: +8%, +7%, +11% with margin crawling. The
idea: *revenue acceleration alone is volume OR price; acceleration WITH margin
expansion is pricing power.*

**Refuted by its own dose-response.** Across 2,673 firings, median 252-day
relative return by QoQ bucket: +2.35%, +2.60%, +4.37%, **−0.30%**. A bigger
signal does not produce a bigger return. SanDisk is a draw from a distribution
whose median is ~2.4% regardless.

**Two things worth keeping anyway:**

* **`derive_q4`** — 17% of quarter-rows followed a gap whose median was **182
  days, p90 184**: exactly two quarters, every time. Q4 is never tagged as a
  quarter in XBRL; it arrives inside the 10-K as part of the annual figure.
  Reconstructed as `annual − (Q1+Q2+Q3)` for FLOW facts only, dated by the
  annual filing. **59,296 rows recovered, 2,273 tickers, coverage 80% → 96%.**
  This hole had been invisible to everything in the repo.
* **The triangulation** (`Q-5`), which disagrees with the consensus optics call.

### §62's mechanism, from Murat's stop-hunting intuition

Paired test — every stopped position against *itself* held, so there is no
benchmark to get wrong:

| stop | n stopped | realised | would have got | recovery | LOO worst |
|---|---:|---:|---:|---:|---:|
| −2% | 58,524 | −2.13% | −1.19% | **+0.93%** | +0.55% |
| −8% | 37,370 | −8.39% | −7.20% | **+1.19%** | +0.88% |

Positive at every level, every year, t +1.91 to +3.53 on 67 monthly blocks. The
recovery on the 89% that get stopped **is** the cost of the stop rule — §62's
"why", measured rather than asserted.

Mechanism is probably not targeted hunting: recovery is *larger* at −8% than
−2%, and the crowded obvious level should be worst if it were being farmed.
Median recovery ≈0 with 49% recovering, so it is a right-tail effect. **The
practical conclusion — don't put a stop there — holds either way.**

---

## 2. Three bugs found, each of which had been silently wrong

| bug | effect | how it was caught |
|---|---|---|
| **`openclaw_client.health()` matched a literal through ANSI codes** — the CLI emits `'Connectivity probe:\x1b[39m \x1b[38;2;47;191;113mok'` | **health() had ALWAYS returned "DO NOT BROWSE". The night runner was never once permitted to browse.** | two agent quests demonstrably succeeded while health called the gateway unreachable |
| a daily-rebalanced equal-weight benchmark | compounded at **+35.1%/yr to 25.1×** vs SPY's 4.53× and a median stock's 2.55×; made the archetype look like −15.7% | **every arm returned the same ~30% hit rate and ~−21% median.** Three different populations cannot lose by the same amount |
| Q4 missing from every quarterly series | one quarter in four, for essentially every filer | gap median 182 days with p90 184 — too regular to be missing data |

The first is the "gate that cannot go green" family, third instance this week.

---

## 3. Built and ready for you

### `scripts/llm_portfolio.py` — the Fable experiment (Murat runs next session)

    python -m scripts.llm_portfolio brief      # point-in-time briefing, whole universe
    python -m scripts.llm_portfolio template   # the shape a book must come back in
    python -m scripts.llm_portfolio freeze books.json
    python -m scripts.llm_portfolio grade      # NAV vs SPY at 1/5/21/126d

$1M per book, no cap on names or weights, several objectives at once, frozen and
content-hashed before outcomes exist, graded net of empirical entry cost.

**The briefing declares what it does NOT have** — analyst targets were 403 on
this tier — so the model is not invited to hallucinate the field. That gap is
now closeable (below).

### `scripts/pull_analyst_targets.py` — free, and it has the revision history

Murat asked whether to pay for an API or scrape. **Neither.** yfinance is already
a dependency and carries it: measured **1.02 s/ticker, 10/10 success, ~51 min
for 3,000 names**.

* `upgrades_downgrades` — **PIT SAFE**, real dated events, firm, prior → current
  target. 443 rows for MRVL, 883 for MU, 3,658 across 12 names.
* `analyst_price_targets`, `eps_trend`, `recommendations` — **SNAPSHOTS, NOT
  PIT**. `eps_trend` looks like history (current vs 7/30/60/90 days) but those
  are today's estimate for a fixed future period, restated. Marked
  `pit_safe: False` on every row.

Scraping 3,000 names would be 9,000–15,000 page loads, 12–40 hours, and blocked.
OpenClaw is for the 20–30 names under actual consideration.

**Wired as `sim_run.u_analyst`** — once per session, out of process, failure is a
SKIP. It must run nightly: the snapshot series only becomes point-in-time from
the day collection starts, and a missed night is a permanent hole.

### The nightly cycle now has seven units

    reconcile → funnel → analyst → rank → plan → grade → learn

`funnel` and `analyst` are both age-gated, once-per-session, out of process, and
refuse without overwriting. `funnel` also treats *rc 0 with an unmoved
`generated_at`* as a failure — a remedy that reports success and changes nothing
is the 2026-09-22 bug in miniature.

---

## 4. The one live call, and it contradicts the analysts

Three independent methods agree the AI bottleneck has moved **past optics to
power**:

| | SEC margin detector | 90-day revisions | OpenClaw evidence |
|---|---|---|---|
| STX / GEV / NVT | **fires** | net +15 / +8 / +6, no lowers | — |
| VRT | does not fire (−0.0pp) | **−4, median −11.6%** | EMEA organic −14.8%, inventory 2× |
| ALAB | does not fire (−3.0pp) | **+8, median +57.3%** | GM 76.3→72%, inventory 2×, WIP 3× |
| LITE / CRDO / MRVL | does not fire | mixed | ASPs falling, inventory build |

Lumentum's own 10-K: cloud transceivers "**+173% due to an increase in shipment
volume**, partially offset by" declining ASPs. Vertiv deferred revenue
**$1.81B → $3.63B** — customers pre-paying, which is what scarcity looks like.

**ALAB is the sharpest case**: analysts raising targets 57% while gross margin
falls and work-in-progress triples. That is narrative outrunning unit economics.

**This is an observation, not a trade.** §63 says the detector has no
dose-response, so it may work as a *filter* while being useless as a *score* —
different claims, and only the first is still open (`Q-5`).

---

## 5. Where the roadmap actually stands

**Closed this week:** §59 (price/volume can't rank), §60 (fundamental ratios
didn't replicate), §61 (horizon extension was one regime), §62 (no exit rule
beats holding), §63 (archetype has no dose-response), §64 (thematic LLM
specialists are anti-signal).

**That is six closed questions and one open positive.** The programme's
demonstrated edge is still 0%, and the honest summary is that we now know a
great deal about what does not work and have one method that does.

**Open, ranked:**

1. **`Q-3`** prune the bench + recalibrate — cheapest positive-EV action available
2. **`Q-4`** revision *flow* (the level is CLOSED/PERVERSE; the flow is untested)
3. **`Q-2`** Fable allocation — built, waiting for Murat
4. **`Q-1`** the 20-year signal dissector — Murat's main ask; needs matched
   controls or it is winner-only forensics
5. **`Q-6`** conditional mean reversion after an index shock
6. **`Q-5`** bottleneck triangulation as a filter, graded as of a past date

**Still owed from before:** the stale-funnel decision is closed (it regenerates
nightly now), but `hack2`'s counterfactual still truncates losses at 1.05× risk
and gains at 20×, and is still printing *"the gate is discarding edge — loosen
it"* off an asymmetrically censored sample. **One change, other repo, not made,
awaiting Murat.**

---

## 6. State of the machines

* **Sim:** `COMPLETED` (`0b2c8110ef68`, 121 cycles, 0 errors). Ready to start —
  6/8/10/12h from the exe.
* **OpenClaw:** gateway running on 18789, `muratclaw` pinned and default,
  **zero messaging channels**, `evaluate` refused, 18 denied domains. Two quests
  completed on `deepseek-flash` returning 76KB of typed JSON with source URLs.
  `health()` now parses correctly — it never could before today.
* **Fleet:** $450,994, −9.8%. 18 positions, 11 stale, 2 undateable. hack2 holds
  nothing and refuses everything.
* **Analyst pull:** running over 3,214 tickers.

---

## 7. What the next session should not re-derive

1. **Grade the ledger before running a backtest.** §64 cost one `groupby` and
   settled more than any panel this month.
2. **Print by year before believing any positive number** — twice now.
3. **When every arm agrees, suspect the benchmark**, not the finding.
4. **A counterfactual computed from outcomes is a hypothesis**, not a result.
5. **Quote a stop in sigma, not percent** — −2% reads like prudence and is 0.93σ.
6. **A gate that cannot go green is broken** — `health()` was red for its whole
   life because of an escape code.
