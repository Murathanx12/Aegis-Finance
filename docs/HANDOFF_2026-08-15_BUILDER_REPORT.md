# Builder report — 2026-08-15, against the brain's order

Order: `docs/HANDOFF_2026-08-15_BRAIN_TO_BUILDER.md` @ `4e33831`.
Reported in the sequence that order asks for.

---

## 1. Production clocks

| | |
|---|---|
| **M1 `pi_ownership_collect`** | fires **10:00 UTC**. Status at time of writing below. |
| **M2 corrected paid night** | pre-open, ~11:50 UTC. Readiness run: **clean**. |
| `pi_ledger_resolve` | fired 2026-08-14T20:30:12Z and **REFUSED** — verified via `/api/optimus/job_receipts`. Unchanged. |

**The collector's receipt was incomplete and was fixed with hours to spare.**
The order requires twelve things to be answerable from that receipt; seven were
absent. Because the first production invocation is the only one that can prove
Railway's egress reaches EDGAR — and a receipt cannot be enriched afterwards,
the day is gone — this was treated as time-critical and deployed (`f2c7b6b`)
before the run. Added at source: `n_unique_accessions`, `n_documents_fetched`,
`failure_classes` (a breakdown, not a count), `events_by_action`,
`n_mechanical`, `n_distinct_actors`, `n_distinct_tickers`, `fetch_seconds`,
`total_seconds`.

The load-bearing pair is `n_attempted` / `n_documents_fetched`. A collector
403-ing on every request still *attempts* the whole day, so a receipt carrying
only "attempted" cannot express the T9 shape at all.
`scripts/verify_ownership_collector.py` names that shape explicitly when it
sees it, and currently reports — correctly — *no production run has written a
receipt yet*, which is the absence of evidence and not a failure.

**M2 readiness (spends nothing) — READY.**

```
frozen prereg   MATCHES (11 fields)
arms            A_snapshot, B_tools, C_tools_only, D_all, B_anon
triggers        40/40 selected from 179 eligible / 182 scored — REACHABLE
model           deepseek-v4-flash        ceilings $12.00 / 3000 calls
features        OK_DATA 1073  OK_EMPTY 3  UNAVAILABLE 16  (1.5%)
snapshot        NOT WRITTEN — the night's slot is still unclaimed
```

## 2. G1 / G2 — the two ordered defects

**Both fixed; every number in `RESEARCH_GYM_1.md` restated.**

### G1 — three denominators, and a calibrated gate

Measured on ^GSPC 1990–2026 at the finding's own 10bp/63d settings, what a
decision-maker with **no skill** scores under the ex-post-best denominator:

| state | always-HOLD | always-SELL_100 |
|---|---:|---:|
| VIX 25–35 | +6.15pp | +10.85pp |
| VIX ≥ 35 | +10.24pp | **+17.31pp** |

Dataset zero's five de-risking decisions, restated:

| | |
|---|---:|
| vs ex-post best *(upper bound, what was reported)* | +26.54pp |
| **vs a pre-declared HOLD** *(unbiased — no selection bias at all)* | **+13.87pp** |
| excess over the state-and-action-matched null | +10.53pp |

The direction survives; the magnitude was roughly doubled by its denominator.
Matchedness is now enforced in code — the first measurement of this null ran on
SPY at 5bps against a finding computed on ^GSPC at 10bps, and `regret_triple()`
**raises** rather than subtract across universe, cost, horizon **or menu**.

The gate: **P(a blameless always-HOLD showing > 1.0pp regret) = 0.931**, so
`MATERIAL_EDGE_PCT = 1.0` labelled 27 of 28 HOLDs failures by construction. It
is now a percentile of the matched null for that state and action — p90 for a
full sell at VIX ≥ 35 is **35.16pp, not 1pp**. Counts invert:

| group | was | now |
|---|---|---|
| de-risking (5) | 5 failures | **4 NO_FAILURE**, 1 state_to_forecast *(suggestive)* |
| holds (28) | 27 failures | **24 NO_FAILURE** |

### G2 — `n_effective`, MDE, and the shape tested as a shape

Every base-rate row now prints `n_effective` (the smaller of overlap and
episode clustering) and its 80%-power MDE. **Not one of the five rows' means is
detectable.** `n=353` for VIX ≥ 35 is **n_eff 5.6**.

The U-shape is a claim that the middle is *lower than* the extremes — a
difference, and §18 requires it tested as one. Against the trough:

| arm | diff | SE | t | verdict |
|---|---:|---:|---:|---|
| VIX 25–35 | +3.04 | 2.48 | 1.23 | not detectable |
| **VIX ≥ 35** | +5.41 | 5.68 | **0.95** | not detectable |

**No arm of the U is detectable.**

The named confound went the other way, too. Deep drawdown **without** panic
returns **−0.67%** at a 52% hit rate; with panic, +6.59%. Panic's marginal
contribution is +7.25pp, SE 7.33, **t = 0.99** — not detectable, but not the
"it's only mechanical rebound" story either. Neither half is established.

**A finding nobody was looking for:** the *adding* decisions — the celebrated
67.4% hit rate — score **−0.57pp against HOLD** and +0.20pp of excess over the
null. Buying on the signal was indistinguishable from staying invested. The
biased denominator hid it completely.

## 3. Research Gym — corpus, tensor, classifications

**REGRET_TENSOR**: state × action × horizon over SPY/QQQ/IWM/XLF/XLE/XLK,
1999–2026, weekly decisions, horizons {5,20,60,120,252}. **425 cells**, each
carrying the action's own return, the ex-post-best regret (upper bound), **the
edge against a pre-declared HOLD** (the only one that can be negative), plus its
own `n_effective` and MDE.

**31 of 425 cells detectable: 24 negative, 7 positive.** Every detectably
different de-risking action lost to holding, worse with stress and horizon
(`sell_100` at VIX ≥ 35: −16.93pp at 120d, **−38.84pp** at 252d). The seven
positive cells are all leveraged-long and clear their MDE by a hair; the two
largest rest on **7.8 effective observations**.

Because leverage beats no leverage on drift almost everywhere, the only
available claim is a **difference** (§18): all eight stress-vs-calm comparisons
point the same way and **not one is detectable**. Consistent in sign,
established nowhere.

No claim language anywhere. `GymResult.as_claim()` still raises; the tensor
declares `citable: False`.

## 4. Autopsy → rule

Six autopsies on dataset zero (worst-first **by regret vs HOLD** — ordering by
regret-vs-best would let G1 choose the study population), each adjudicated on
five foreign slices with the parent excluded mechanically.

| | |
|---|---:|
| mechanisms proposed | 6 |
| replies dropped as untestable | 0 |
| explained only their parent | 0 |
| **exportable** | **0** |

Strongest, and the only one worth naming: `vix ∈ [25,35) and ret_1m_pct ≤ −5 →
buy_50` against a `hold` control — **2 of the 3 required slices** (GFC +5.12pp
vs MDE 3.82; taper +4.94pp vs 2.45), on foreign securities and foreign decades.
Still REFUSED, and would stay refused with a third: export also requires a
frozen pre-registration and forward certification. **The Gym cannot certify
itself.**

One rule was genuinely *refuted* (the 2019-12-31 "sell into low volatility and
strong momentum" mechanism, −8.82 / −2.99 / +2.17 / −0.29). The machinery kills
as well as it passes.

§20: six proposals, six lineage rows. This is a search of size six.

## 5. Teacher Library

Production events: **none yet** — the collector has not fired. Local corpus
stands at 1,589 events / 485 resolved actors.

**Actor Surprise (T1) is data-blocked, and the measurement is now in the doc.**
`P(action | actor history)` needs history; the corpus holds **one month**, and
the median actor has **one observation** (234 actors with 1 event, 87 with 2, 43
with 3). Estimating the distribution of an actor's behaviour from one
observation is not a weak estimate — it is a restatement of the action, and it
would produce a number for every actor that means nothing for almost all of
them. What *is* computable without history: role, independent-insider clusters,
opposing actions within one issuer, 10b5-1 status, event proximity. What would
unblock the rest is a per-actor Form 4 backfill — PIT-safe, a baseline rather
than a track record, **not authorized**, and not to be confused with a COPY-LAB
historical fill.

COPY-LAB eligibility: unchanged, still gated on M1. `ACTIVIST_13D` still
blocked. No fake history anywhere.

## 6. Defects found by running checks rather than by review

1. **The autopsy pipeline reported DEAD for every mechanism, and was wrong.**
   Precursors read `sp500_1m_return_pct`; probes carried `vix` and
   `drawdown_pct`; every lookup raised and `evaluate_slice` swallowed each raise
   as "did not fire". Fifteen clean zeros that looked exactly like discipline.
   **A bug that manufactures a kill reads as the system working** —
   NEGATIVE_RESULTS §37. Fixed at three depths: unevaluable episodes counted and
   reported UNTESTED (never DEAD); a `TRANSFERABLE_FEATURES` vocabulary enforced
   at construction; both corpora carrying it, with the runner halting otherwise.
2. **`realised_vol_20d = 0.0`** — a cold rolling window filled with zero. This
   repo bans `fillna(0)` on feature matrices; a state vector is a feature matrix
   with one row. Unmeasured is now `None` and comparing `None` raises.
3. **A units error inflated 75% of the tensor's findings** — the clustering gap
   was in strided units while positions were in days. Expected to be cosmetic
   because overlap *looked* binding; 357 of 425 cells turned out episode-bound
   and **detectable cells fell from 126 to 31**. It also reversed the one
   nominally significant difference (t 2.47 → 0.83). NEGATIVE_RESULTS §38.
4. **`llm_research.ask` discarded `finish_reason`** and defaulted to
   `max_tokens=2000` on a reasoning model — the identical defect that voided
   IIF-1 Night 1, sitting in a second module. Now recorded, warned, returned.
5. **`--readiness` spent the night's one snapshot slot.** It spends no money,
   but froze a production snapshot dated *now*; run hours before a pre-open
   night it guaranteed the staleness refusal — through the one command whose
   documented purpose is to be safe. Now assembles without freezing.
6. **Its own final instruction then went stale**: the report ended with
   `--reuse-snapshot`, which after the fix points at a snapshot that no longer
   exists. Fixed and pinned — half a fix is how receipts got written where
   nothing could read them.
7. **Assembly time is charged against the freshness budget and nobody measured
   it.** `decision_ts` is stamped when assembly *starts* and the guard allows 45
   minutes; measured assembly is **~20 minutes**. Now recorded on the snapshot
   and printed in the readiness report.
8. **The guard only ever checked the start.** A night starting 20 minutes stale
   and running 40 ends with its tool arms reading a world 60 minutes newer than
   the timestamp their forecasts are graded from — and the exposure is
   *differential* (tool arms only), the same bias structure that voided Night 1.
   `decision_lag_minutes_at_end` is now on every receipt. Measured, not
   enforced: aborting mid-night buys contaminated forecasts *and* loses the
   night.
9. **The fast suite was writing ~624 rows per run into a tracked ledger**
   (3.9 MB accumulated) and silently rewriting the 2026-08-15 rehearsal receipt.
   Both redirect to tmp; the tree is clean after a full run for the first time.
10. **`read_lineage` silently dropped corrupt rows** — in the function that
    reports this campaign's own §20 multiple-comparison count. A truncated write
    would have shrunk the recorded search with no trace, in the direction that
    makes every deflation too generous. Unreadable rows are now retained as
    counted placeholders.
11. **`menu_hash` was built to catch a drift and then never compared.** Adding
    one policy to `POLICY_MENU` would have silently raised every historical
    regret figure against an unchanged null. Now enforced.
12. **A test seam that was not a seam.** The receipt-completeness tests
    monkeypatched `OwnershipFormsAdapter._collect` — an *instance* attribute
    assigned in `__init__`. The class patch silently created a new attribute,
    the live SEC fetch ran anyway, and one test **passed** on a real
    NOT_YET_PUBLISHED response that happened to carry every key it asserted.
    `collect_and_append` now takes `collect=` / `append_fn=`.

## 7. Tests / SHAs / deploy

| | |
|---|---|
| `34155be` | M3 — G1/G2, three denominators, calibrated gate, n_effective + MDE |
| `3eabe74` | M4 + M5 — autopsy, tensor, and the run that killed everything wrongly |
| `f2c7b6b` | collector receipt completeness + `verify_ownership_collector` |
| tests | **4,100+ fast, 0 failing** |
| prod | verified live on `f2c7b6b`, status ok, 7 jobs, NAV fresh |

## 7b. Budget

`DEFAULT_BALANCE_USD` was still **$37.12** — stale by Murat's $20 top-up, which
the brain's §3 ratified. Updated to **$57.12** (`BALANCE_AS_OF 2026-08-15`) after
checking it is **not** part of the frozen pre-registration; a change to a frozen
field would have made the night REFUSE rather than merely misreport. The three
tests that hard-coded `37.12` now reference the constant, because a dated fact
that changes when someone tops up should not fail a test suite for the one
reason that is not a defect.

At $57.12 over 40 nights the planning average is **$1.428/night** — which is
exactly the brain's stated $1.43 break-even, so that figure was computed from
the topped-up balance and the two agree.

## 8. Next bottleneck

**Forward evidence.** Nothing has changed about the fact that IIF-1 has zero
graded nights and COPY-LAB has no live teacher stream. Everything built this
session makes the Gym's answers *honest*; none of it makes them *evidence*, and
the two clocks are the only things that can.

After those: the corpus is the constraint. Actor Surprise needs actor history
that one month of collection cannot provide, and the transfer slices — currently
six ETFs and five periods — are what decides whether a mechanism at 2 of 3
slices reaches 3 for a real reason or a lucky one.
