# Session review and handoff — 2026-08-15 evening → 2026-08-16 morning

Written to be **reviewed and contested**, not accepted. Every number below is
either reproducible from a committed script or was read off a live surface at a
stated time. Section 9 lists the claims I think are most likely to be wrong, so
the review can start there instead of hunting.

Authorisation for this stretch: *"you have the full night 8+ hours run the shells
and tests while I sleep"* — unattended, plus the standing *"don't sacrifice on
quality or results."*

---

## 1. The accounting

| | |
|---|---|
| **dollars spent** | **$0.00** — zero paid LLM calls, declared in advance |
| serious distinct hypotheses attempted | **5** (N8, N2, N4, N6, D4) |
| cheap kills | **2** (D4; the reactive-corpus hope) |
| unresolved / underpowered | **1** (N8's headline — could not be identified) |
| survivors | **1** (N6, with a caveat that reverses its product implication) |
| findings that changed architecture | **3** (N6's ordering, N2's build order, the atlas grammar) |
| defects found and fixed | **3** (§55 armed; §56 live; §56b self-inflicted) |
| **new investment candidates** | **ZERO** |
| tests | **4,314 → 4,321 local**, **4,303 → 4,310 CI-sim** |
| commits | 8 (`f091809` … `6a0c825`) |

**Zero new investment candidates is the headline the order asked to stay
visible.** This session produced no tradeable signal. It produced a
specification for what would count as one, and removed three things that would
have stopped the programme shipping.

**Why $0.** The paid IIF-1 night was structurally impossible — its window opens
2026-08-16 19:30 UTC and the session ran before it. I declared zero spend in
advance rather than finding cheap things to spend on, because unattended spend
against a trial ceiling is exactly what the governor bounds, and a governor is
not a substitute for someone being awake. This is *not* an instance of
"minimise API calls": the discovery work was compute-bound, and every hypothesis
that could have used an LLM was one where compute answered the same question
better.

---

## 2. Verified state

| | |
|---|---|
| repo tip | **`6a0c825`** |
| working tree | 0 dirty, 0 unpushed |
| CI | **green** on `6a0c825` (red on `4d16013`, see §5.3) |
| production | **`6a0c825`**, confirmed by `deploy.commit` |
| `scheduler.nav.all_fresh` | **true** |
| prod overall status | **DEGRADED** — from the prediction ledger (25 overdue), correctly |
| `fred_health` | **ok** (was `UNKNOWN`), 19 FRESH / 4 STALE_USABLE, 0 degraded reasons |

### Commit ledger

| SHA | what |
|---|---|
| `f091809` | the overnight protocol, declared **before any number existed** |
| `fe5a966` | **N8** — the corpus cannot size itself; the design curve |
| `0a0781b` | **N2** — twelve markets are worth 1.31× the US |
| `a6ff2ff` | **N4** — 85% of exceptional moves had no warning |
| `59d953b` | **N6** supported and free; **D4** killed *(CI red — my flaky timing test)* |
| `b2f429b` | atlas grammar unblocked; the CI time bomb defused; timing test fixed |
| `de0b00b` | overnight report |
| `4d16013` | **§56** FRED health re-derived from the served payload *(CI red — §5.3)* |
| `6a0c825` | **§56b** `ci_env_sim` taught that CI has no secrets |

---

## 3. Research results

### 3.1 N6 — the one economically meaningful positive, and its caveat is the finding

One feature set, one model class, one set of embargoed walk-forward folds,
12 securities, **82,954 rows**, three targets differing only in *which moment*:

| horizon | sign (AUC) | abs return (IC) | realised vol (IC) |
|---|---|---|---|
| 5d | 0.4967 *(MDE 0.025)* | **0.294** | **0.531** |
| 20d | 0.5092 *(MDE 0.034)* | **0.244** | **0.622** |
| 60d | 0.5014 *(MDE 0.051)* | **0.169** | **0.567** |

SUPPORTED at every horizon by the rule declared before the run; survives
shrinking `n_effective` from six folds to three. The four earlier results
pointing this way were not four coincidences.

**Then the rival was tested rather than noted.** Volatility is persistent, so a
model handed `rv20` can score a large IC by copying it. Against the *free*
predictor — trailing 20-day realised vol, alone, no model, paired by fold:

> **model minus baseline: −0.085 to +0.025. Not detectable at any horizon,
> either target. At 60d it is materially worse.**

**Consequence, and it sharpens rather than softens.** Build the volatility head:
it works, costs nothing, and feeds sizing, ruin constraints and `gamma*`
immediately. **Do not expect ML to add to it.** And *"we forecast volatility
better"* is **not** the defensible product — it has to be built on what a single
trailing number cannot express: co-movement structure, conditional tails, regime
transitions, drawdown shape.

### 3.2 D4 — killed

Direction is not hiding in the high-magnitude subset. Conditional AUC
0.4934 / 0.5089 / 0.5007; differences −0.006 / −0.003 / +0.004 against MDEs
0.037–0.054. **The coin is a coin in the wide part of the distribution too.**

### 3.3 N8 — the corpus cannot determine how much corpus it needs

The declared kill **fired** (median `n_required` 305 > threshold 200) — and then
§37 was applied *to the kill* and changed the answer. `n_required ∝ 1/d²` and
`d` is measured on `n_effective ≈ 2`, so the requirement spans **0.9 to 1,534
episodes**. Reporting "305, change the question" would have been the week's third
false kill **and would have looked like rigour.**

Reframe, which is what makes it actionable — dispersion IS well estimated, so
corpus size becomes a **decision**:

| minimum effect worth acting on | episodes needed (crisis, sd 17.7pp) | (calm, sd 1.5pp) |
|---|---|---|
| 1pp | 2,456 | 17 |
| 3pp | 273 | 2 |
| 5pp | 98 | 1 |
| **10pp** | **25** | — |

**The scarcity is dispersion, not history**, and it sits entirely in the states
every mechanism is about: crisis dispersion ≈ **12×** calm, `n ∝ sd²`, so the
same edge costs **144× more episodes** exactly where we keep asking.

Consistency check that was not two separate facts: the Gym's own recalibrated
35.16pp bar needs **2** episodes, and its cells carry ~2.

### 3.4 N2 — twelve markets and thirty-six years are worth 1.31× the US

Threshold fixed as a **frequency before any count was read** (VIX ≥ 35 = 3.83% of
US days ⇒ the same percentile of each market's own realised vol). **152 raw
episodes** vs the US's 19.

* by correlation on stress days (ρ̄ = 0.466): twelve slices are worth **1.96**
  ⇒ **24.8 independent episodes, 1.31× the US alone**
* by timing: **80 of 152** episodes begin >42 days from any US crisis

The two measures disagree by 3×, **and the answer survives it**: a 10pp minimum
effect is reachable on both, 5pp on neither. First specification
TRANSFER_ATLAS_V1 has ever had.

**Build order changes: Asia first, Europe last.** India 75% novel crises, Korea
60%, Hong Kong 59%, Japan 53% — against France 25%, Germany/UK/Switzerland 36%.
Europe's crises *are* the US's crises.

### 3.5 N4 — 85% of exceptional moves had no warning from anything

**85.6% (20d) / 87.6% (60d)** of bottom-decile moves had no precursor fire. The
library fires on **15.3% of ALL days**, so its 12–17% coverage **is its base
rate**: lift 0.82–1.15 against MDEs 0.25–0.62 ⇒ **no coverage at either tail,
either horizon.**

Pattern inside the null: **it marks the TOP tail better than the BOTTOM at every
horizon** — a library built from SELL autopsies marks recoveries.

⇒ Coverage is now a metric with a baseline (lift 1.0), and the roadmap flips:
**validity was never the binding constraint; coverage is.**

### 3.6 §54 — the atlas was unreachable in principle

Every precursor is written over `vix`; **exactly one market has one**, so N2's
152 episodes could not be evaluated by a single existing rule. Not missing data —
the grammar could not express the question, and more collection would not have
helped.

`realised_vol_20d` does not fix it, for a reason worth keeping: **portable as a
number, meaningless as a threshold** (frequency-matched bars: Korea 57.3%
annualised, Australia 27.2% ⇒ a level rule selects a *country*).

`stress_pctile` (expanding window, so a rank never sees its own future) is now in
`TRANSFERABLE_FEATURES`. **Faithfulness checked BEFORE reach and only moderate:
recall 72.5%, precision 48.4%, Jaccard 40.9%** ⇒ a **related state selector, not
a synonym**, and every result computed through it carries that. Firing rate
varies 1.8% (Korea) to 6.0% (US) — an expanding percentile penalises markets
whose worst crisis came early (Korea 1997). Stated rather than smoothed.

**Bought:** episodes evaluable outside the US **0 → 101**; markets a library rule
can run in **1 → 9**.

---

## 4. What the research jointly argues

N4 says **85% of exceptional moves have no precursor at all**. N8 says the
mechanisms we do have need **273 crisis episodes** at a 3pp bar. N2 says the
entire world supplies **25 to 80**.

> Together: **validating crisis-conditioned mechanisms harder cannot work** — not
> because the discipline is wrong, but because the sample does not exist and
> never will.

N6 says where the sample does exist. **The cross-sectional second-moment question
has thousands of independent observations; the crisis-conditioned first-moment
question has twenty-five.**

Opening question I would put to the next phase: **what does a risk model know
that a trailing volatility number does not?** — because tonight's check says that
is exactly where the free answer stops.

---

## 5. Defects

### 5.1 §55 — a CI time bomb, found six hours before it fired, now confirmed

`test_the_live_ledger_canary_is_healthy` asserted `status == "ok"` against the
**real** ledger. Campaign forecasts fall due 2026-08-16:

```
2026-08-15   ok        0 overdue     <- CI green here, 17:14 UTC
2026-08-16   DEGRADED  110 overdue
2026-08-17   DEGRADED  201 overdue
```

CI runs in UTC and Railway gates deploys on CI. Worse than §44/§47: those clear
by editing code; this clears only when a human runs an **attended, irreversible**
resolution — so the pipeline freezes until someone wakes, with every unrelated
fix stuck behind another person's chores.

**Now confirmed empirically rather than predicted.** After UTC crossed midnight,
`ledger_health()` returned **`DEGRADED`, `n_overdue: 110`** — exactly as
forecast — and the **full fast suite stayed green in that world**, so the ledger
canary was the only test that turned on the date.

### 5.2 §56 — the health page reported on its process, not on its data

Found by doing what `verify-prod-after-deploy` exists to force: reading the live
surface instead of trusting green tests. `/api/health/full` read `fred_health:
UNKNOWN`, all 23 series `UNAVAILABLE`, `fetch_passes: 0` **and**
`last_no_fetch_reason: null` — unreachable in combination, since `_prewarm_cache`
records a reason on every failure path.

Railway logs settled it in two lines:

```
2026-08-15 17:42:48  Fetching macroeconomic indicators from FRED (parallel)...
2026-08-15 17:42:52    Loaded 23/23 FRED series          <- 3.6s, the body ran
2026-08-16 02:06:31,754  Prewarmed: market data
2026-08-16 02:06:31,763  Prewarmed: FRED data            <- 9 MILLISECONDS
```

The process restarted 8.4h later, `@cached(ttl=86400)` served from the SQLite
disk cache, and **the decorator returns before the body** — so `record_pass`
never ran.

**The defect stated precisely.** `fred_health` was built to answer *"are the FRED
inputs trustworthy?"* It measured *"did the fetch body execute in THIS
process?"* Those agree only until something serves the data without re-fetching
it — which is what a 24-hour cache is for.

The module's scope note refuses to persist "a health claim that outlives the
evidence for it". **Right principle, false premise:** the evidence does not die
with the process. The payload is in the disk cache and is still being served.
The restart destroyed the **record**, not the data. Different lifetimes; the
module assumed one.

**Harm, checked rather than asserted** — see §5.5, because my first version of
this claim was wrong. The real harm: `degraded_reasons()` names a never-loaded
critical series only when `passes_seen > 0`, and a restart zeroes that:

| | `degraded_reasons` | status |
|---|---|---|
| cold pass, ICSA missing | **1, named** | DEGRADED |
| restart into that same warm cache | **0** | UNKNOWN |

ICSA is still absent from the served payload for the rest of the TTL. The page
stops saying so. **The original ICSA incident, reached through the cache instead
of the fetch.**

**Fix re-derives; it does not remember.** `record_served()` runs on every read of
the payload and reads the artefact in hand; the payload carries its own
`fetched_at`, so a cache hit reports the real age instead of manufacturing a
fresh pass. Idempotent on `fetched_at`. `health()` gained `served_fetch_at`,
`served_age_hours`, `served_from_cache`.

**Census:** an AST sweep of every `@cached`/`@lru_cache` function in `backend/`
containing a status or health write found **exactly one** — this one. Not
systemic.

### 5.3 §56b — my own push turned CI red

`4d16013` was green on **4,321 local** *and* **4,310 CI-sim**, and CI failed.
**CI exports no secrets** — its pytest step sets `AEGIS_IIF1_PREREG_ABSENT_OK`
and nothing else — so `api_keys.has("fred")` is True here (`.env`) and False
there. My four new tests leaned on the ambient key and received `{}`.

`ci_env_sim` exists to end exactly this, and had modelled what CI **hides** (the
sibling repo) but not what CI **lacks** (keys). It now blanks seven API keys —
**by mutating the `api_keys` singleton in place**, because every service does
`from backend.config import api_keys` and holds the original object: rebinding
`config.api_keys` would be invisible, and blanking `os.environ` alone does not
move a dataclass built at import.

**Verified rather than assumed:** with the test-side fix stashed, the improved
simulator reproduces CI's exact four failures. The full suite with secrets
blanked is **4,310 passed**, which also says no *other* test was quietly
depending on a real key.

### 5.4 The family — fifth instance in a week

| § | the wrong world |
|---|---|
| §0 | CI's world (the sibling repo) |
| §44 | the calendar's world (a Sunday opening bell) |
| §47 | the clock's world (a default frozen at import) |
| §55 | the operational backlog's world (a test asserting live health) |
| **§56** | **a process's world, where the artefact's was needed** |
| **§56b** | **a simulator's world, missing a dimension** |

One root question every time: **where is this value actually read, and what world
does it describe?** Correct arithmetic against the wrong world remains the house
failure mode.

### 5.5 Two self-corrections that matter more than the fix

**(a) My first framing was too strong, and the test caught it.** I claimed a dead
FRED and a warm cache produce identical health pages, and wrote a test asserting
they were indistinguishable. **It passed on the unfixed code** — a dark source
with a *cold* cache still runs, still records misses, still reads `DEGRADED`. The
overstatement was caught instead of shipped, and that test is now a guard on the
pre-existing behaviour the fix must not trade away.

**(b) Reviewing my own fix found a regression it introduced.** `record_pass`
substitutes a last-known-good series for a failed critical one and labels it
`STALE_USABLE`. That substituted series **is** in the cached payload — so the
first draft reported a carried-forward print as `FRESH` after a restart,
**trading a false alarm for a false reassurance, which is the worse direction**,
with every test passing. Measured directly: `substituted=None` → `FRESH`,
`substituted=['initial_claims']` → `STALE_USABLE`. The payload now carries which
names were carried forward, and the test was verified to **fail** without that
argument before being allowed to pass with it (§37).

---

## 6. Failures and waste — mine

Listed because a session that only reports its wins is not reviewable.

1. **Pushed a red CI** (`4d16013`), blocking deploys until `6a0c825`. Cause in
   §5.3. Root: I ran the CI *simulator* and treated it as equivalent to CI, which
   is the exact error the simulator's own docstring warns about.
2. **Overstated a claim** and had to retract it mid-work (§5.5a).
3. **Introduced a regression in my own fix**, caught by review rather than by
   tests (§5.5b).
4. **Left an unused `import time`** that would have failed ruff and turned CI red
   — caught pre-commit by a static check, but it should not have been written.
5. **Ran a network-heavy script concurrently with the test suite**, turning a
   2.5-minute run into **83 minutes**. Pure wall-clock waste; the result was
   unaffected.
6. **Edited source under a running suite twice**, invalidating both runs and
   forcing kills and re-runs. This is a repeat of a known lesson from the prior
   session and should not have recurred.
7. **`59d953b` also went out red** (a flaky timing test of mine that used an
   instant stub, so five arms finished inside one Windows clock tick and wall
   time was 0.0). Fixed in `b2f429b`.

Net: **two red CI pushes in one session.** Both were caught and fixed within the
session, neither reached a state where production ran wrong code, but both
blocked the deploy gate temporarily.

---

## 7. What was NOT done, and what is NOT verified

**Deliberately not done (attended / irreversible / clock-bound):**

* **The paid IIF-1 night.** Window opens **2026-08-16 19:30 UTC**; latest safe
  start **2026-08-17 12:20 UTC** (11:25 at p90). One attempt, hard stop, no H1
  read. Neither 08-15 nor 08-16 is a session.
* **`resolve_campaign_ledger --commit`.** Irreversible; yours.
* **The LIVE_FORWARD quarantine.** Irreversible and outward-facing; untouched.

**Not run from the P3 programme:** D1 GRAPH-REACTION-GAP, D2
MECHANISMIZED-REFLECTION, D3 WINNER–MATCHED-LOSER FACTORY, D5
TEACHER-SKILL-DECOMPOSITION, N7 (insider clusters). P4 learning loop and P5
experiment accounting not started.

**Explicitly NOT verified — the honest limits:**

* **The §56 fix's own path has not been exercised in production.** Prod reads
  `served_from_cache: False`, `served_age_hours: 0.26` — a redeploy rebuilds the
  container, so the disk cache starts empty and this was a *real* fetch. It would
  have read `ok` without my fix too. **The cache-hit path fires on the next
  in-container restart**, and only then is the fix live-verified. Anyone
  reviewing should treat "prod went UNKNOWN → ok" as **insufficient evidence**.
* The 4 `STALE_USABLE` FRED series in prod are the vocabulary working (observation
  older than 2× publication lag), not a fault — but I did not chase which four or
  why.
* N2's ρ̄-based and timing-based supply measures disagree by 3×. The *decision*
  survives; the *quantity* is a range, not a number.
* `stress_pctile` agrees with the incumbent VIX rule on only 41% of the union of
  their firings. Every atlas result computed through it inherits that.

---

## 8. Open decisions and next steps

### 8.1 Yours — attended, irreversible

**(a) The campaign resolution.** Re-verified today against a byte-identical copy:

> **110 due · 110 would resolve · 0 unpriceable · health returns to `ok`**
> priced from a fresh fetch · real ledger SHA-256 `ff458c77…` **unchanged**

Two names (APLT, SLNO) price off your 2025-11-07 sheet rather than surviving
bars; the run discloses both with and without them. Command:
`python -m scripts.resolve_campaign_ledger --commit`

**(b) Two ledgers — a design decision I flagged rather than made.**

| | records | overdue | specialists | path |
|---|---|---|---|---|
| production | **112** | 25 | 12 | `/data/optimus/predictions.jsonl` (Railway volume) |
| repo | **20,073** | 110 | 24 | `backend/data/optimus/predictions.jsonl` |

Disclosed at WARNING, by design: *"holds 19961 record(s) absent from the
persisted ledger — NOT copied (the persisted ledger is authoritative once
non-empty)"*. Nothing is broken and nothing auto-resolved. But **the campaign's
~20k forecasts are not in production**, and `campaign_resolution_readiness`
grades the repo file. Which ledger is authoritative — and whether prod's 25
overdue should be resolved separately — is yours.

**(c) The paid night**, at or before 12:20 UTC on 08-17.

### 8.2 Mine, next session, in order

1. **Confirm the §56 cache-hit path live** once prod restarts in-container —
   `served_from_cache: true` with a real `served_fetch_at`. Until then the fix is
   shipped but not live-verified.
2. **Build the volatility head** (N6's actionable half) — and design it from the
   start around what `rv20` *cannot* express, since the baseline check says the
   model adds nothing to `rv20` alone.
3. **Open the "what does a risk model know that rv20 does not" question** as a
   pre-registered programme: co-movement structure, conditional tails, regime
   transitions, drawdown shape.
4. **Asia-first transfer collection** (N2's build order), specified against a
   **declared 10pp** minimum effect rather than an undeclared one.
5. Remaining P3 items (D1, D2, D3, D5, N7) — but see §4: D3
   (winner–matched-loser) is the one most aligned with what the numbers now say.

---

## 9. Claims most likely to be wrong — start the review here

1. **"The cache-hit path is deployed but unexercised."** I inferred the container
   filesystem is rebuilt on redeploy from `served_from_cache: False` plus a 0.26h
   age. If Railway actually preserves `backend/.cache` across deploys, my
   reasoning about *why* it read False is wrong even though the field is right.
2. **N6's "the model does not beat rv20".** Paired by fold, but with
   `n_effective` small; the interval −0.085 to +0.025 contains zero comfortably,
   which is a *failure to detect*, **not** a demonstration of no difference
   (§19). It should not be quoted as "ML adds nothing", only as "ML was not shown
   to add anything at this power".
3. **N8's design curve** assumes the dispersion estimate transfers to future
   crisis regimes. Dispersion is better estimated than `d`, but "well estimated"
   is doing real work in the reframe.
4. **N2's 1.31×.** Depends on ρ̄ = 0.466 measured on stress days only, and the
   timing-based measure disagrees 3×. I claim the *decision* is robust; I do not
   claim the multiplier is.
5. **§56's harm characterisation.** I got this wrong once already (§5.5a). The
   current claim is narrow — `degraded_reasons` goes silent — and I believe it is
   right, but it is the claim I have most recently been wrong about.
6. **"Not systemic" (the AST census).** It matched on name patterns
   (`record_`, `_status`, `health`, …). A status write named something else would
   not have been found.
7. **The two-ledger finding.** I observed the states and read the migration
   warning; I did **not** reconstruct why the 02:06 boot reported 20,073 records
   and the 04:07 boot reported 112. Something about volume mounting changed
   between them and I did not chase it.

---

## 10. Canon earned this session

* **If a function is cached, the instrumentation inside it is cached too** —
  anything that must be true on every call belongs outside the decorator.
  (Added to `silent-fragility-audit` #7.)
* **A singleton every module imported by value cannot be replaced, only mutated.**
* **A simulator of another environment is only as good as the dimensions it
  models, and every dimension it omits looks exactly like a passing test.**
* **A negative result needs evidence exactly as a positive one does** — N8's kill
  fired, and checking the kill as hard as a pass (§37) reversed it.
* **A new instrument's first positive is the one that looks like it working** —
  applied to `stress_pctile` (faithfulness measured before reach) and to the
  substitution test (verified to fail before allowed to pass).

Prior sections: `NEGATIVE_RESULTS.md` §49–§56.
