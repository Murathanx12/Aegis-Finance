# Session report — Opus 5 executing the 2026-08-15 handoff

**Executed** `docs/HANDOFF_OPUS5_2026-08-15.md` (Fable's binding order, `bb68bba`).
**Result:** Orders 1, 3, 4, 5, 6 complete. **Order 2 is complete except its
final step — the paid night — which is deliberately deferred and blocked by a
guard written this session.** Order 7 (WORLD-MODEL-v1) remains unbuilt, as
ordered.

`aegis-finance` @ `8bd510c`, `Aegis module` @ `f5367f0`, both pushed.
4,018 fast tests green (66 new).

---

## 1. The headline: Night 1's cause, and what it was doing to the trial

**`MAX_TOKENS = 1600`.** Measured live against the frozen Night-1 snapshot:
every barren cell returned `finish_reason="length"` with `tokens_out` exactly
**1600**; the two that produced came in at 1396 and 1591. One survived by **nine
tokens**. Re-run at 4000, the same eight cells produced 8/8.

The mechanism is not reply length. `deepseek-v4-flash` is a reasoning model and
`max_tokens` bounds **thinking plus answer**: CSCO spent 3,238 output tokens on
a 681-character reply; a `B_tools` cell spent **7,186** on 1,617 characters.
Below the budget the model needs, it never reaches the JSON at all — which is
why truncated replies arrived as an **empty string** rather than half an object.

**It was not a uniform tax.** Tool arms gather dossiers → longer prompts →
longer thinking → more truncation. The ceiling silenced the **treatment arm of
the primary contrast** four times as often as its control (`B_tools` 8/10 barren
vs `A_snapshot` 15/40). Had Night 1 completed, A-vs-B would have been biased by
a constant appearing in no registered document. **The information guard did not
just save $0.40 — it stopped a biased trial from accruing.**

The inherited suspect — a size bound in percent where a fraction is required —
is **refuted twice**: `return_sign` carries `threshold=None` and skips that
check, so a percent bug yields `n_forecasts == 1`, never 0, and every barren
cell was exactly 0; and every parsed reply carried a proper fraction. That bug
was real — it belongs to the 2026-08-11 swarm's six void records, which is
exactly where the suspicion came from.

**A second confound, found while fixing the first.** The tool layer's own rule
is *"now is point-in-time by construction"* — tools read the live internet when
called. The loop ran **arm-major**, so on a 200-cell night the last arm saw
hours more of the world than the first, in fixed order. That is the primary
contrast confounded by loop order. The loop is now **cell-major**: the five arms
of one cell run seconds apart against the same world, and an early stop leaves
every arm the same trimmed prefix instead of voiding.

## 2. Why the paid night did NOT run, and when it should

Not reluctance — a guard written this session refuses it.

Tool arms read live data, so a night is only honest if it runs close to the
`decision_ts` its forecasts are graded from. Night 1 ran **16 minutes** after
its snapshot; nothing enforced that, it held by habit. The 2026-08-14 production
snapshot was frozen pre-open at 07:50 ET and is **immutable by design**; by the
time the diagnosis was complete it was 3+ hours old and the market had opened.
Running against it would have handed the four tool-bearing arms three hours of
hindsight on a one-day horizon, stamped with a pre-open decision time — the
exact class of defect just fixed.

`assert_decision_time_fresh` now refuses a production night whose snapshot is
older than **45 minutes**.

**So: run it pre-open on 2026-08-15**, against a fresh snapshot:

```bash
python -m backend.services.iif1_run --readiness      # spends nothing
python -m backend.services.iif1_run --reuse-snapshot # the first dollar
```

Everything upstream is done and clean: root cause pinned by tests, `MAX_TOKENS`
registered in the frozen prereg (so drift is now a refusal), and a **full
five-arm chain-aware rehearsal** passing — 50 chains, 0 barren, 240 calls
resolved, against Night 1's 50/50 barren. The rehearsal now swaps only the
**transport**, so chain minting/collection/amendment stay inside the simulation;
before, injecting the client bypassed them and it reported `n_chains: 0`.

### The funding number needs Murat

Priced from real probes at the corrected ceiling: `A_snapshot` **$0.00107/cell**,
a tool arm **$0.00624/cell** ⇒ a full 40-trigger × 5-arm night ≈ **$1.04**, and
40 nights ≈ **$41.61 against a $37.12 balance**.

That is above R1's **$0.60** automatic threshold, so by the ratified rule the
top-up decision goes to Murat rather than self-funding. Murat's "don't worry
about the cost, I will top up" removes the friction, not the gate — the number
is reported because the rule says it is his call. Note the earlier $0.41
projection was computed from a night whose cells were dying at the ceiling; it
was the cost of a broken configuration.

## 3. D4 was asked backwards, and the resolver was four days from acting on it

The warning said 19,961 records were missing from the persisted ledger. The
guard's `legacy_only` is a set difference over **full-record content hashes**:
20,073 image records − 19,961 absent ⇒ intersection exactly **112**, the
volume's entire contents. **The persisted ledger is a strict subset of the
campaign ledger.** Four corroborations that it is specifically the *first* 112
rows: 12 distinct specialists (first 112 have 12, last 112 have 14); prod's
`n_void: 6` matches the only six `void_reason` records in all 20,073, at indices
58–68; one distinct model; last-written 2026-08-12.

- **The 19,961 are CAMPAIGN_FORWARD and alive** — the population `ABLATION_FWD`
  certifies against, first resolutions **2026-08-16**. Merge stays refused.
- **`LIVE_FORWARD`'s true size is ZERO.** The module docstring claimed those 112
  were "the deployed product's own accrual". That was false and is corrected.

**And the hazard was dated.** Those 112 rows' `resolves_after` dates begin
**2026-08-16**, with 25 due that month. `pi_ledger_resolve` is nightly,
unattended, and correctly pinned to `live_forward` — a population that owns
nothing. On the 16th it would have written outcomes onto campaign swarm rows and
manufactured "the deployed product's forward record" out of history. An outcome
written onto a record is what makes it evidence; nothing unmakes that later.

`resolve_due` now **refuses** when the population holds records and none are its
own. The guard is narrow: an empty ledger is not refused, because an empty
ledger has nothing to grade.

**Left for Murat** (irreversible, outward-facing, not a session's call):
quarantine those 112 off the volume under a dated migration receipt.
Recommended attended, after the 08-16 resolutions so the two events cannot be
confused. Not urgent — the guard already prevents the false claim.

## 4. The Gym, and what dataset zero actually says

`RESEARCH-GYM-1` registered once. Three walls in code: `GymResult.as_claim()`
raises; `LineageRow` carries `parent_failure`; `request_export` refuses without
≥3 transfer slices, a prereg and forward certification, **and bars the episode
that inspired a rule from proving it**.

**The taxonomy needed a mode it did not have.** The first run classified all five
de-risking failures as `forecast_failure` — true, and an artefact: under
"expected down, went up", a sell before a rally can barely classify otherwise.
Murat's directive is sharper than the label — *"stress detection itself was
correct; the failure came from mapping high stress → zero exposure"* — and
separates three layers, not two: **perception** (VIX 57, measured), **inference**
(expect down — the error), **action** (sell). So `state_to_forecast_failure` was
added, decided against the state's own historical **base rate** rather than
against the outcome: contradicting the base rate is wrong in a way the data
already knew and is *learnable*; agreeing with it and losing is an unlucky draw,
and "fixing" that is fitting noise.

Base rates, 1990–2026, 63-day forward — **Gym output, a hypothesis, not evidence:**

| state | n | P(up) | mean 63d |
|---|---:|---:|---:|
| VIX 20–25 | 1824 | 0.643 | **+1.56%** |
| VIX 25–35 | 1248 | 0.732 | +4.60% |
| VIX ≥ 35 | 353 | 0.731 | **+6.97%** |

**The relationship is U-shaped, not monotone.** The worst forward returns follow
the *middle* bucket; the best follow the *highest-stress* bucket. The engine
sells above VIX 25 — precisely where history most says to be long. All 5
de-risking decisions classify `state_to_forecast_failure`, mean regret
**+26.5pp**. The classifier discriminates rather than labelling everything one
way: within 28 HOLDs it splits 7 state-to-forecast against 7 unlucky, plus 8
sizing and 5 timing.

This converts a sentence the README has carried for months into a measurement,
and sharpens it: it is not that stress is bullish, it is that **the map from
stress to expected return is non-monotone and the engine assumed it was
monotone.** It establishes nothing about any fix.

## 5. Teacher Library: sells exist

Old path: code `P`, acquisitions only, one ticker at a time. On 25 real Form 4s:
**60 transactions, 20 sells, 2 buys** — it would have kept 2 rows out of 60. A
corpus like that cannot disagree with "insider buying is bullish".

New path is driven by the SEC daily index (universe-free, point-in-time by
construction) and keeps every code both directions, Form 3 holdings, roles, and
10b5-1 as a tri-state. One real cycle: 1,098 index rows → **512 documents**,
coverage 1.000, **0 parse errors, 1,567 events — 516 SELL / 87 BUY / 964
compensation mechanics**, 482 actors, 294 tickers. Idempotent. Scheduled as
`pi_ownership_collect`, daily 06:00 ET, with a receipt.

Two defects that only running it for real could find: the live index uses
`YYYYMMDD` (my fixture invented `YYYY-MM-DD`, so the parser matched the
invention and reported a Thursday of 1,098 filings as `OK_EMPTY`); and joint
filings appear once per reporting entity — 1,098 rows were 512 documents, one
appearing **eleven times** — so we fetched documents 11× over and `findtext` read
only the first owner, losing the rest exactly on the cluster case.

## 6. What the next session must do, in order

1. **The paid night, pre-open 2026-08-15.** Hard stop, one attempt. If it voids,
   the void reason is again the deliverable — do not retry a third time without
   Murat.
2. **Report the funding number and get Murat's word** before the 40-night
   accrual starts. ≈$1.04/night, ≈$41.61 total vs $37.12.
3. ~~Verify `pi_ledger_resolve`'s 20:30 UTC run.~~ **DONE — verified live at the
   end of this session.** It fired on schedule at **2026-08-14T20:30:12Z** and
   returned `status: REFUSED`, *"every one of 112 LIVE_FORWARD record(s) is
   content-identical to a CAMPAIGN_FORWARD record"*. So the §3 adjudication is
   confirmed by production itself rather than by analysis alone, and the guard
   demonstrably held on the first run after deploy. Read it with
   `GET /api/optimus/job_receipts`.

   `pi_ownership_collect` correctly reports `exists: false` — *"no run has
   written one yet"* — its first run is 2026-08-15 06:00 ET. **Verify that one
   by its receipt**, and remember local success is not evidence: Railway egress
   is a different network, and the insider collector once passed twelve tests
   while 403-ing on 100% of prod fetches.
4. **2026-08-16, attended:** first CAMPAIGN_FORWARD resolutions,
   `--population campaign_forward`, dated receipt. Never pooled with
   LIVE_FORWARD.
5. **Verify the first production `pi_ownership_collect` run.** Local success is
   not evidence: Railway egress is a different network, and the insider
   collector once passed twelve tests while 403-ing on 100% of prod fetches.
6. **AUTOPSY-TO-RULE-1 (R5)** — the episode substrate now exists. Optimus reads
   a resolved episode and its surface, emits a structured hypothesis with
   contemporaneous and post-outcome evidence kept *separate*, plus an executable
   rule; the rule is then evaluated only on foreign crashes, stocks and decades.
7. **Wire the ownership events into COPY-LAB eligibility.** `ACTIVIST_13D` stays
   blocked until 13D ingestion exists.

**Still not authorized:** WORLD-MODEL-v1; new covariance descendants; pooling
forward populations; reads of accruing trials.

## 7. Defects logged this session

| # | Defect | Status |
|---|---|---|
| N1 | `MAX_TOKENS=1600` killed 23/50 cells and biased the primary contrast | FIXED, registered in the frozen prereg |
| N2 | Arm-major loop made arm order a proxy for information age | FIXED — cell-major |
| N3 | No guard on snapshot staleness; PIT protocol held by habit | FIXED — 45-min refusal |
| N4 | `finish_reason` discarded before anyone could see it | FIXED — carried through |
| N5 | `spend(since=…)` truncated timestamps to the DAY; a $0 rehearsal reported $0.115 and the nightly ceiling counted unrelated spend | FIXED — exact, trial-scoped |
| N6 | `LIVE_FORWARD` is 112 campaign copies, not a live population | ADJUDICATED; resolver refuses; volume cleanup is Murat's call |
| N7 | `pi_ledger_resolve` wrote no receipt — "didn't run" indistinguishable from "nothing due" | FIXED |
| N8 | Daily-index fixture invented a date format; parser matched the invention | FIXED, both spellings pinned |
| N9 | Joint filings fetched 11× and only the first owner parsed | FIXED |
| D2 | 2 torn `llm_calls.jsonl` lines (handoff said 3) | Quarantined with addresses; health DEGRADED |
| D5 | README overclaimed IIF-1/COPY-LAB | FIXED — new ⚪ ARMED badge |
