# Handoff — 2026-09-24/25. The ledger had the answer; three guards were broken.

Continuation file. Read this, then `docs/RESEARCH_QUEUE.md`.
Supersedes `HANDOFF_2026-09-24_THE_LEDGER_WAS_THE_ANSWER.md` (same session, later).

---

## RESULTS SCOREBOARD

| line | state |
|---|---|
| best historical net strategy vs market | **none.** §59 / §60 / §61 / §63 all closed |
| best forward paper strategy | fleet **$450,994 / $500,000, −9.8%**; PC-PAPER flat at $1,000,000 (refuses to trade a measured-negative ranker) |
| **new actionable finding** | **§64 — a structured evidence PROCESS forecasts at +8.97% Brier skill out of sample; nine thematic LLM personas score −27.98% and their optimal weight is ZERO** |
| second finding | **§62's mechanism measured**: a stopped position recovers +0.93% to +1.19%, at every level, in every year |
| independent selector count | unchanged |
| LLM spend | **$0.00 on research**; two OpenClaw quests + 46 forecasts on `deepseek-flash` |

**RESULT IMPROVEMENT: the first positive out-of-sample forward result in the
programme — and it is about method, not about markets.**

---

## 1. §64 — the evidence was already bought and nobody had read it

`predictions.jsonl` had been accruing since 2026-08-11: **25,439 probabilistic
forecasts**, each frozen with a horizon and a resolution date *before* the
outcome existed. Forward evidence — no window chosen, nothing re-sliced.

    overall Brier      0.2625        (later 0.2678 on more rows)
    climatology        0.2244        always predict the base rate
    SKILL            -17.01%   ->    -19.35%
    calibration gap  +17.0pp         every arm says more than happens

Held out — first half by date fits the recalibration, second half scores it:

| family | n test | raw skill | recalibrated | weight | discrimination |
|---|---:|---:|---:|---:|---:|
| `investigator:*` (evidence process) | 2,325 | **+4.38%** | **+8.97%** | 0.65 | **+16.7** |
| thematic personas (9 arms) | 5,027 | **−27.98%** | −0.00% | **0.00** | −2.0 |

The nine personas have **negative discrimination** — they assign higher
probabilities to things that do not happen. That is anti-signal, and their
optimal weight is exactly zero. Skill lives at **h=1** (+5.75%) and is gone by
h=5 (+0.09%).

**Verified robust:** after recovering 2,781 more graded rows (§4 below) the
result *strengthened* — overall −19.35%, all five investigators still positive,
all nine personas still negative, discrimination split unchanged. It was not an
artefact of which rows happened to be gradeable.

**Do next:** `Q-3` — turn the nine thematic specialists off (a spending
decision, not a research one), apply the 0.65 shrink at the point of use, ask at
h=1.

---

## 2. The forecaster built from that result

`scripts/night_investigator_forecast.py`. Every design choice is read off §64
rather than picked: process not persona, h=1, shrink 0.65. The evidence packet
is fully point-in-time — price/liquidity features, the latest SEC quarter dated
by its **filing**, and the 90-day revision flow filtered strictly to the past.
The model is told what is already closed (§59, §62, §63, and that target LEVELS
are CLOSED/PERVERSE) so it does not spend its answer rediscovering them.

**40 forecasts frozen, 0 refused, resolving 2026-09-28.**

    OKTA 0.58  ...  INTC 0.48   INTU 0.44
    raw mean 0.515, spread [0.44, 0.58]

It discriminates rather than defaulting, cites 10–14 named evidence fields each,
and reports `low` confidence where the packet is thin. Mean at the base rate
with real dispersion — the opposite of the +17 to +30pp overconfidence that
condemned the personas.

The first attempt refused **55%** on unparseable JSON — nested objects breaking
on unescaped quotes. Flattening the schema took it to 0%. A **degraded parse**
backstops it and is deliberately not a *repaired* one: it lifts the model's own
number and records `facts_used: None` rather than reconstructing reasoning that
did not survive.

**Not a trade.** A probability with information in it needs a
probability-to-return calibration before it can be sized, and that does not
exist. §61 is what happens when a number is quoted before it has one.

---

## 3. §63 — the SanDisk archetype, built and refuted

SanDisk filed **+21.4% QoQ with margin +3.6pp on 2025-11-07 at $239**; it is
$1,766 now. Western Digital over the same window ran +8/+7/+11% with margin
crawling and returned 176% against 638%. The idea: *acceleration alone is volume
or price; acceleration WITH margin expansion is pricing power.*

**Refuted by its own dose-response.** Median 252-day relative return by QoQ
bucket: +2.35%, +2.60%, +4.37%, **−0.30%**. A bigger signal does not pay more.

**Kept anyway — `derive_q4`.** 17% of quarter-rows followed a gap whose median
was **182 days, p90 184**: exactly two quarters, every time, because XBRL never
tags Q4 as a quarter — it arrives inside the 10-K as part of the annual figure.
Reconstructed as `annual − (Q1+Q2+Q3)` for FLOW facts only, dated by the annual
filing. **59,296 rows recovered, 2,273 tickers, coverage 80% → 96%.** That hole
was invisible to everything in this repo.

---

## 4. Recovered: 2,911 stranded records → 130

`forecast_grader` had printed "2,911 records past their resolution date and
still unresolved" on every run and kept the ledger canary DEGRADED for it. They
were never unresolvable: **105 of 110 stranded tickers were simply absent from
the price panel** — ETFs (XBI, SMH), REITs (AVB, DLR), a tail of microcaps a
universe screen dropped. Something forecast on them; nothing fetched a price.

`scripts/pull_forecast_bars.py` pulled **99 of 99, 41,703 rows**, into a
**separate** panel that only the grader unions. Separate on purpose: the main
panel is read by the ranker and fingerprinted by `u_rank`, so appending would
both rewrite a file a live session is reading *and* silently widen the ranker's
universe with names its own eligibility screen rejected.

**Graded 14,703 → 17,484.** The sim now reports `130 wait on a bar`.

The remaining 6 are genuinely non-equity (`CL=F`, `ES=F`, `ZN=F`, `GC=F`,
`DX-Y.NYB`, `^VIX`). They are reported `PERMANENTLY_UNPRICEABLE` and **not
voided** — voiding edits a tamper-evident ledger and is Murat's call.

---

## 5. Analyst data: free, and it has the revision history

Murat asked whether to pay for an API or scrape. **Neither.** yfinance is already
a dependency: measured **1.02 s/ticker, 10/10 success**, and the full pull was
**392,201 dated revision rows across 2,982 tickers, 2011→2026, 0 failures,
66.8 minutes**.

| source | PIT? |
|---|---|
| `upgrades_downgrades` | **SAFE** — real event dates, firm, prior → current target |
| `analyst_price_targets`, `eps_trend`, `recommendations` | **NOT PIT** — snapshots, marked `pit_safe: False` |

`eps_trend` *looks* like history (current vs 7/30/60/90 days) and is today's
estimate for a fixed future period, restated. Reading it as history would be a
look-ahead disaster.

Scraping 3,000 names would be 9,000–15,000 page loads, 12–40 hours, and blocked
long before finishing. **OpenClaw is for the 20–30 names under actual
consideration** — which is what it did, finding Lumentum's own 10-K attributing
+173% transceiver growth to *volume* "partially offset by" falling ASPs.

Wired as `sim_run.u_analyst`. **It must run nightly** — the snapshot series only
becomes point-in-time from the day collection starts and a missed night is a
permanent hole.

---

## 6. Four guards that were broken, three of them the same guard

| bug | effect | how it was caught |
|---|---|---|
| `openclaw_client.health()` matched a literal through **ANSI codes** | **health() had ALWAYS returned "DO NOT BROWSE"** — the night runner was never once permitted to browse | two agent quests demonstrably succeeded while health called the gateway unreachable |
| `data_credential()` returned the first pair that **existed**, list starting at retired **HACK3** | every caller got a revoked key and a 401 since 2026-09-22, with five working pairs never reached | a 401 on a key that "was there" |
| a daily-rebalanced equal-weight benchmark | compounded at **+35.1%/yr to 25.1×** vs SPY's 4.53×; made §63 look like −15.7% | **every arm returned the same ~30% hit rate and ~−21% median** — three different populations cannot lose by the same amount |
| the session heartbeat, in **three** places | a healthy session read `UNCLEAN` | a live process at 322 MB with a visibly working child, labelled dead |

The heartbeat, specifically, was wrong three times in one day:

    cycle boundary     beat only when a CYCLE started
    inter-cycle idle   MIN_CYCLE_PERIOD_S (300) == STALE_AFTER_S (300)
    inside a unit      one unit longer than 300s

So it is now **general**: a daemon thread beats every `IDLE_BEAT_S` for as long
as a unit runs, naming the unit and its elapsed seconds. Verified live —
`16:25:33`, `(60s)`, `(120s)`, `RUNNING` throughout the pull that had just
broken it. Tests assert the beater does **not** outlive its unit, which would
report a dead process as alive: the opposite failure and the worse one.

---

## 7. What I broke

`predictions.jsonl` is a **tracked file that accumulates rows continuously** —
` M` in `git status` is its normal state. A commit message came out mangled
(backticks in an unquoted heredoc), I amended it, and a force-push was
**correctly** rejected by branch protection. I realigned with
`git reset --hard origin/main` — to fix a *message* — and it discarded
**~1,200 uncommitted rows**: 40 forecasts from this session and roughly 600
written by other processes between 2026-09-11 and 2026-09-22.

The 40 are restored from their receipt under their original `made_at`, each
marked `RESTORED` with `input_snapshot` naming the receipt rather than
pretending to carry the original evidence packet. **The ~600 are gone** — no
commit or mirror has them.

`--soft` would have done the job. So would doing nothing. Recorded in memory as
[[feedback-never-reset-hard-a-repo-that-tracks-a-growing-data-file]].

---

## 8. State of the machines

* **Sim:** `RUNNING`, session `f3d54fa01531`, pid 123424, **cycle 15**,
  `resume_count 1`, ends **2026-09-25T00:25:29Z**. Seven units:
  `reconcile → funnel → analyst → rank → plan → grade → learn`.
* **Sleep:** the machine suspended mid-session on 09-24; the process was frozen,
  not killed, and resumed with a stale heartbeat and a dead socket.
  `sim_run.keep_awake()` now suppresses **idle** sleep. It **cannot** stop a lid
  close, a manual sleep, or a flat battery — nothing an application calls can.
  On this machine `STANDBYIDLE` is already 0 on AC and 600s on battery, so it
  covers the battery case. **The currently-running session predates that patch;
  the next start picks it up.**
* **OpenClaw:** gateway up on 18789, `muratclaw` pinned and default, **zero
  messaging channels**, `evaluate` refused, 18 denied domains, health **READY**
  (it never could be before today).
* **Ledger:** 24,879 rows, **17,484 graded (70%)**, 40 forecasts resolving
  2026-09-28.
* **Fleet:** $450,994, −9.8%. hack2 holds nothing and refuses everything.
* **CI:** green through `72bad0e`; `e2109be` pushed.

---

## 9. Ready for Murat

**`scripts/llm_portfolio.py` — the Fable experiment.**

    python -m scripts.llm_portfolio brief      # point-in-time briefing
    python -m scripts.llm_portfolio template   # the shape a book must return in
    python -m scripts.llm_portfolio freeze books.json
    python -m scripts.llm_portfolio grade      # NAV vs SPY at 1/5/21/126d

$1M a book, no cap on names or weights, several objectives at once, frozen and
content-hashed before outcomes exist, graded net of empirical entry cost.
Briefing verified: **3,598 names, 1.6 MB, ~418,000 tokens**, fundamentals on
2,230, `inflection_flag` on 117, **four declared gaps** so the model cannot
hallucinate analyst targets, and the five standing findings handed over so it
does not re-derive §59.

---

## 10. The one live call, contradicting the analysts

Three independent methods agree the AI bottleneck has moved **past optics to
power**:

| | SEC margin detector | 90-day revisions | OpenClaw evidence |
|---|---|---|---|
| STX / GEV / NVT | **fires** | net +15 / +8 / +6, no lowers | — |
| VRT | does not fire | **−4, median −11.6%** | EMEA organic −14.8%, inventory 2× |
| ALAB | does not fire (−3.0pp) | **+8, median +57.3%** | GM 76.3→72%, inventory 2×, WIP 3× |

Vertiv deferred revenue **$1.81B → $3.63B** — customers pre-paying, which is
what scarcity looks like. **ALAB is the sharpest divergence**: analysts raising
targets 57% while gross margin falls and work-in-progress triples.

**An observation, not a trade.** §63 says the detector has no dose-response, so
it may work as a *filter* while being useless as a *score* — different claims,
and only the first is open (`Q-5`).

---

## 11. What the next session should not re-derive

1. **Grade the ledger before running a backtest.** §64 cost one `groupby` and
   settled more than any panel this month.
2. **Print by year before believing a positive number** — twice now.
3. **When every arm agrees, suspect the benchmark**, not the finding.
4. **A counterfactual computed from outcomes is a hypothesis**, not a result.
5. **Quote a stop in sigma, not percent** — −2% reads like prudence and is 0.93σ.
6. **A gate that cannot go green is broken** — `health()` was red for its whole
   life because of an escape code.
7. **Never `reset --hard` here.** A tracked, continuously-growing data file
   means uncommitted rows exist at all times.
8. **Presence is not validity.** Verify a credential with one call before using
   it; `data_credential()` now does.
