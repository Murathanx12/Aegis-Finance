# NIGHT-14 — WHY THE BOOK MOVED, AND THE TWO THINGS WE CAN ACTUALLY GRADE

Murat asked: *"my portfolio dropped a bit yesterday, lost 1k. why did this
happen, llm should try to reason multiple times and compare itself to reality
on why. this is the learning we want."*

The engine now answers that in three layers, and **it never names a cause.**
One day of data cannot identify one — the world where Iran did not sign and the
book still fell is not observable. So the question was split into a part that is
arithmetic, a part that is checkable, and a part that is neither and is
therefore refused at the door.

| Layer | What it is | What it is worth |
|---|---|---|
| Attribution | shares × price change, market/sector/residual | ground truth, no model involved |
| Hypotheses | 7 independent DeepSeek lenses, structured JSON only | unproven, preserved plural, never ranked |
| Grading | cross-asset **coherence** now + forward **skill** later | the only two measurements that exist |

**The two graded things are never added together.** A corroboration hit says
the stated mechanism was coherent with the rest of the market that day; an
incoherent explanation is refuted, which is worth knowing. It is *not*
forecasting skill and never becomes skill however many days accumulate. Skill
lives only in the forward `PredictionRecord`s, scored by Brier against
climatology by the existing resolver.

Files: `backend/services/why_moved.py`, `backend/routers/why_moved.py`,
`backend/tests/test_why_moved.py` (47 tests, offline),
`scripts/run_why_moved.py`, config block at the end of `backend/config.py`.

---

## 1. The date, and why it is not the one asked for

The run was launched for **2026-08-11**. Yahoo had SPY's 08-11 close but not the
close of eleven of Murat's twelve names — the vendor publishes the index hours
before it publishes a $2 biotech. Grading the book on that day would have
reported a P&L the book never took, so the attribution refused, loudly, and the
runner walked back one session and said so:

```
SKIPPED 2026-08-11: no usable closes on 2026-08-10 -> 2026-08-11 for
  ['AARD','ABSI','BHVN','DKNG','HUBS','KYTX','NTLA','PRCH','QUBT','SLDP','SOC']
NOTE: 2026-08-11 does not price the whole book; graded 2026-08-10 instead
```

**The day of record is 2026-08-10** (previous close 2026-08-07). Note that
Murat's "-1k yesterday" is his broker's number for a different day; the -$233
below is 08-10 measured from the recovered book. The two are not the same
statement and are not reconciled here.

## 2. Deterministic attribution — 2026-08-10

| | |
|---|---|
| Book value 08-07 → 08-10 | $40,625.50 → $40,392.60 |
| **P&L** | **−$232.90 (−0.573%)** |
| SPY | −0.030% |
| Book beta (weighted) | 2.19 |
| Market leg | −0.065% = **−$26.46** |
| Sector leg (net of market) | +1.134% = **+$460.52** |
| Idiosyncratic residual | −1.642% = **−$666.96** |

Per position, worst to best:

| | ret | P&L | contribution | beta |
|---|---|---|---|---|
| AARD | −4.30% | −$340 | −83.7 bps | 3.05 |
| AMSC | −5.43% | −$89 | −21.9 bps | 3.44 |
| PRCH | −2.65% | −$84 | −20.7 bps | 1.92 |
| QUBT | −2.72% | −$75 | −18.5 bps | 3.70 |
| BHVN | −0.82% | −$36 | −8.9 bps | 1.03 |
| KYTX | −0.88% | −$18 | −4.3 bps | 2.52 |
| SLDP | +0.86% | +$12 | +3.0 bps | 3.19 |
| NTLA | +0.67% | +$20 | +4.9 bps | 2.27 |
| DKNG | +1.00% | +$36 | +8.9 bps | 0.65 |
| ABSI | +0.90% | +$48 | +11.8 bps | 3.34 |
| HUBS | +2.59% | +$55 | +13.4 bps | 0.53 |
| SOC | +7.16% | +$238 | +58.6 bps | 0.25 |

Sector returns that day: Energy +4.66%, Health Care +1.67%, Consumer
Discretionary −0.16%, Industrials −0.31%, Information Technology −0.88%.
Contributions sum to the total to floating tolerance (tested), every position
priced, no sector unmapped, no beta fallback.

**The reading, and its limit.** On a day the market did nothing (−0.03%), the
book lost 0.57%, and both factor legs point the other way: the sector mix was
*worth +$461*. The residual is −$667 and one name (AARD, −4.3%) is half of it.
That is a decomposition, not a diagnosis — "idiosyncratic" means *the two
factors do not account for it*, not *stock-specific news happened*.

## 3. The seven lenses

Each lens is called separately; they never see each other's output. Full run
(`docs/conviction_replay/why_moved_2026-08-10.json`), plus one re-run of
`geopolitical` after a token-limit fix
(`..._2026-08-10_geopolitical_rerun.json` — that lens minted nothing in the
first run, so no forecast is double-counted and no lens ran twice).

| lens | hypotheses | rejected | external hit rate | derivable (not evidence) | minted |
|---|---|---|---|---|---|
| company_news | 4 | 0 | 4/5 = 80% | 3/3 | 4 |
| macro_rates | 1 | **3** | 1/1 | 1/1 | 1 |
| geopolitical (1st run) | 0 | **1** | — | — | 0 |
| geopolitical (re-run) | 4 | 0 | 5/6 = 83% | 3/3 | 4 |
| sector_factor | 4 | 0 | 2/2 | 6/6 | 4 |
| options_vol | 4 | 0 | 2/2 | 6/6 | 4 |
| revisions | 4 | 0 | 3/4 = 75% | 4/4 | 4 |
| skeptic | 4 | 0 | 4/5 = 80% | 4/6 | 4 |
| **batch (1st run)** | **21** | **4** | **16/19 = 84.2%** | 24/26 = 92.3% | 21 |

### The four rejections — as interesting as the acceptances

* **macro_rates ×3 — recommendation language.** Three of its four hypotheses
  (`energy-rally-lifts-long-duration`, `biotech-idiosyncratic-selloff`,
  `tech-weakness-hits-growth`) reached for an action and were refused unread.
  One lens produced all three: the tic is systematic, not scattered.
  *The offending text was not retained*, which makes a rejection count
  unauditable — you cannot tell a lens with a tic from a regex that is too
  greedy. Fixed: rejections now carry `matched_terms` and a
  `refused_text_excerpt`.
* **geopolitical ×1 — unparseable JSON.** The answer was truncated mid-object
  at ~8,700 characters by a 2,400-token ceiling. The module counted it as a
  rejection and kept running (that is the designed behaviour) but the call was
  wasted. `WHY_MOVED_MAX_TOKENS` is now 4,000; the re-run produced 4
  hypotheses, 0 rejections.

Nothing else was rejected — no ungradeable hypothesis reached the store,
because the parse rule refuses any hypothesis with neither a checkable
cross-asset assertion nor a forward claim. That rule is the whole difference
between this and commentary.

### Corroboration, and the circularity that had to be removed

The first scoring said **89% (40/45)**. It was inflated: the prompt hands each
lens the book's own returns, the benchmark's and each held sector's, so "XLE
up" from a lens just told *Energy +4.66%* is the input read back and hits every
time. Split by whether the answer was already in the prompt:

| class | record |
|---|---|
| book tickers (return given) | 4/4 = 100% |
| sector ETFs + SPY (returns given) | 20/22 = 91% |
| **strictly external (nothing in prompt)** | **16/19 = 84.2%** ← the only quotable number |

The classification is computed **from the prompt payload itself**
(`derivable_assets(lens_input(...))`), not from a hand-kept list, so if someone
adds a field to the prompt the split follows automatically instead of rotting
into a wrong one. The artifact was **re-scored, not re-run**
(`--regrade`): fixing a scoring bug by calling the model again would have
written a second batch of correlated forecasts about the same day to repair
arithmetic.

The three external misses are the informative rows:

* `company_news/market-neutrality` — required ^VIX **down** ≥5%; VIX was **+3.8%**.
* `revisions/healthcare-idio-selloff` — required XBI to underperform; XBI **+0.42%**.
* `skeptic/sector_rotation_healthcare` — required IBB **down**; IBB **+1.17%**.

And in the geopolitical re-run, `no-macro-shock` asserted VIX would *not* move
≥5% — it moved 3.76%, graded a miss on the magnitude leg while its GLD leg hit.
That is exactly the intended behaviour: the same hypothesis can be partly
coherent and partly refuted, and both are recorded.

**What 84.2% does and does not mean.** It means: on this one day, 16 of 19
stated cross-asset requirements about instruments nobody had told the model
about were actually present. That is a coherence score on *n = 19 assertions
from one day* — it says nothing on its own, it is not skill, and it must never
be quoted beside a Brier score as though the two were the same currency.

### CANON §20 — the batch checked against itself

**14 effective distinct ideas out of 21 hypotheses (ratio 0.667).** Seven
components collapsed:

| collapsed component | lenses |
|---|---|
| the SOC/energy rally | sector_factor + options_vol + revisions |
| SOC/energy again, second wording | company_news + skeptic |
| tech weakness | company_news + skeptic |
| health-care moved on idiosyncratic news | sector_factor + options_vol |
| tech weakness was idiosyncratic | sector_factor + options_vol |
| high beta magnified an idiosyncratic loss | sector_factor + options_vol |

`sector_factor` and `options_vol` collapsed together **four times** — on this
day they were close to one forecaster with two names. The denominator for
anything said about this batch is 14, not 21.

## 4. Forward claims — 25 PredictionRecords minted

21 from the main run + 4 from the geopolitical re-run, all written to
`backend/data/optimus/predictions.jsonl` under specialists `why_moved:<lens>`.

**The first why_moved records resolve 2026-08-16** — against a ledger whose
earliest existing resolution was 2026-09-12. The short horizons pulled the
first grade forward by 27 days, which was their entire purpose.

One refusal path was exercised in testing rather than live: a `threshold ≥ 1.0`
(percent where a decimal fraction was required — the bug that produced six
guaranteed-wrong records on a previous run) is surfaced as a counted refusal
with the ledger's own message, never coerced.

**A monoculture, and it is a defect.** 23 of the 25 claims are `return_sign` at
horizon 1, twelve of them at probability exactly 0.50. A coin flip you called a
coin flip accrues n quickly and teaches nothing. The prompt now explicitly asks
for horizon and observable variety and names this batch as the failure to
avoid; that change is **untested against a live run** and should be checked on
the next one.

## 5. Honesty constraints, and where each one bit

1. **No ground-truth cause.** Enforced in the docstrings, the `epistemics`
   block of every response, and the absence of any ranking. Competing
   explanations from seven lenses are stored side by side; nothing in the code
   can collapse them into a winner.
2. **Ungradeable ⇒ rejected and counted.** 4 rejections on the live run, each
   named with its lens and reason.
3. **Degraded ≠ fabricated.** No key / API failure / unparseable JSON ⇒
   explicit status, zero hypotheses, attribution still returned. Exercised
   live: `geopolitical` went dark in run 1 and the other six were unaffected.
4. **Descriptive only.** Recommendation language is refused, not sanitised —
   three live refusals, all from one lens.
5. **Coherence ≠ skill.** Added after the audit: the two instruments are
   reported under separate keys with separate notes, and the combined rate is
   named `corroboration_hit_rate_combined` so it cannot be mistaken for the
   headline.
6. **Loud pricing failure.** A book that cannot be marked raises rather than
   returning a plausible zero; the vendor-lag walk-back happens in the runner,
   prints every skipped day, and names the day it graded.

## 6. Not done / left for the main session

* **The router is written but NOT wired.** `backend/main.py` was being edited
  by another session tonight, so per the brief it was left alone. Two lines:

  ```python
  from backend.routers import why_moved as _why_moved   # noqa: E402
  app.include_router(_why_moved.router)
  ```

  Endpoints: `GET /api/why-moved/attribution`, `/explain`, `/lenses`.
* **No frontend page.** The response object is JSON-safe and shaped for one.
* **The prompt's horizon-diversity fix is unvalidated live** (see §4).
* Nothing was committed. Everything is in the working tree.
