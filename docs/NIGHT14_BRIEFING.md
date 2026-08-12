# NIGHT-14 BRIEFING — make the reasoning gradeable

**Written 2026-08-12, before the work.** Contract for the night. The prompts and
the external reviews that produced it are archived verbatim in
`NIGHT14_EXTERNAL_REVIEW.md`.

Murat's instruction: *"I wont be here for multiple hours so run very long
simulations and shells, calls from api to learn and build the network. dont let
it sit still, continues learning is key, make it test and learn at my absence."*

---

## §1 — The one sentence

The reviewer's diagnosis is correct and the programme accepts it:

> **Stop treating the LLM as a narrator sitting beside the engine. Make it a
> population of forecasters living inside an environment that relentlessly
> grades what they say.**

But the review's own framing hides the actual bottleneck, and naming it is the
whole design of tonight. The problem was never the NUMBER of calls. It is that
**the grading clock was too slow to be a learning loop at all.**

`HORIZONS` began at 5 trading days. Every forecast the specialists wrote was
therefore unfalsifiable for a month, and the ledger's first grade fell on
2026-09-12. A loop whose feedback arrives after the next twelve build sessions
is not a loop; it is a queue. Adding calls to a system that cannot grade them
faster buys more unlabelled data at higher cost — precisely the failure the
reviewer warns about in §8 while proposing more calls in §1.

So the ordering tonight is: **make reasoning gradeable FAST, then spend.**

Two changes do the real work:

1. **`HORIZONS` now includes 1 and 2 trading days.** A claim about yesterday's
   move is a claim about the next day or two; forcing it onto a 5-day horizon
   graded a different claim than the one made.
2. **Cross-asset corroboration grades INSTANTLY.** This is the night's one
   genuinely new idea and it is worth stating plainly, because the reviewer
   proposed the mechanism without noticing what it makes possible. When a
   specialist says *"Iran peace optimism faded, so oil rose, yields rose, and
   long-duration tech underperformed"*, those clauses are assertions about a day
   that **has already happened**. They can be checked against real prices in
   seconds. A specialist that blames geopolitics for every decline, but whose
   stated cross-asset signature is repeatedly absent, loses reliability the same
   evening rather than next quarter.

That converts the learning clock from **31 days to under a minute** for the
explanation layer, while the forward-forecast layer keeps its honest longer
horizons. Everything else tonight is downstream of that.

---

## §2 — The reviewer's P0-P13, answered

Thirteen phases is more than one night. Refusing to pretend otherwise is part of
the contract. Each item gets one of: **TONIGHT**, **PARTIAL**, **DEFERRED** (with
the reason), or **REFUSED** (with the reason).

| # | Item | Verdict | Why |
|---|---|---|---|
| P0 | Ledger persistence across deploys | **TONIGHT** | Confirmed real and blocking: `LEDGER_DIR` resolves inside the Docker image while the volume is `AEGIS_DATA_DIR`. Every forecast written since the spine shipped dies on the next deploy. This is the same defect class as NIGHT-13's uncalled resolver and it must not survive the night. |
| P0 | Scheduler job-set canary | **TONIGHT** | NIGHT-13's rolling deploy silently deleted `pi_ledger_resolve`; the mechanism is understood and the detector is cheap. |
| P0 | Seed forward shadow books | **DEFERRED** | Carried since NIGHT-13. The seeding path does not exist in code and inventing one unattended risks a fake inception on a track record whose only value is that it was never touched. This is an attended job (see `seed-a-lane`). |
| P0 | Optimus freshness / MCP context health | **PARTIAL** | The staleness risk is real and the reviewer is right that a perfectly-executing agent with stale context does the wrong research. Auditing MCP internals is out of scope for a night already building the attribution engine; what ships is the check that `refresh_aegis` actually ran. |
| P1 | WHY-MOVED causal attribution | **TONIGHT** | The centrepiece. Directly answers Murat's question. |
| P2 | Expand prediction ledger horizons | **TONIGHT** | 1 and 2 added; see §1. |
| P2 | Intermediate non-price observables | **DEFERRED** | The four existing observables all resolve from adjusted closes with no vendor whose definition can drift. Adding estimate-revision or catalyst-occurrence observables means adding a vendor to the resolution path, and a forecast that resolves differently depending on who you ask is not a forecast. Worth doing carefully later; not worth doing fast. |
| P3 | Centralized LLM telemetry | **TONIGHT** | Cannot measure information-per-dollar without it. |
| P3 | Contextual-bandit research router | **DEFERRED** | A router that allocates budget across specialists needs reliability estimates to route on. Those estimates start accruing tonight and do not exist yet. Building the router first would route on noise. |
| P4 | MODEL-ORCHESTRATOR-BENCH-1 | **PARTIAL** | Murat asked directly. A scoped paired benchmark runs tonight, and its limits are stated rather than hidden — see §5. |
| P5 | Portfolio Gym | **DEFERRED** | Correctly identified as high-value. It is also a multi-night build, and starting it badly tonight is worse than starting it properly later. The reviewer's own sequencing agrees: synthetic known-answer worlds FIRST. |
| P6 | Five-way learning stack | **DEFERRED** | Same reason. Note the reviewer's most useful line here is a warning, not a build: *do not build one monolithic neural network.* Recorded as canon-adjacent guidance. |
| P7 | EXIT-RL | **DEFERRED** | Depends on P5. |
| P8 | GEO-1 geopolitical intelligence | **PARTIAL** | The geopolitical specialist ships tonight inside WHY-MOVED and starts accruing graded corroboration immediately. The *trial* — does LLM-extracted geopolitical state add information beyond oil/VIX/rates/trend — needs a PIT event dataset that does not exist yet. Building the data collection first is the right order, and tonight's corroboration grades ARE that collection. |
| P9 | Event graph / second-order beneficiaries | **PARTIAL** | Pre-registered tonight as `THEME-CASCADE-1` so the hypothesis is frozen BEFORE anyone looks at the SK Hynix / SanDisk / WDC / Kioxia / Vicor pattern. The reviewer explicitly asked for this and was right to. |
| P10 | Evolutionary policies | **DEFERRED** | ARENA-1 already measured what this costs and what it returns (384 genomes, zero clearing the bar). A second run needs a new instrument, not a bigger pool — see the corpse-lint rule. |
| P11 | Teacher library | **PARTIAL** | `WINNER-GENOME-1` is the teacher-library question in its most answerable form, and it is what Murat actually asked about. Runs tonight. |
| P12 | Product: three risk budgets, four modes | **DEFERRED** | The IC page already produces complete portfolios at any capital. Three named risk budgets is a real upgrade but it is product work competing with the learning loop, and Murat's instruction tonight was learning. |
| P13 | Forward tournament | **DEFERRED** | Depends on shadow-book seeding (attended). |

**Refused outright:** nothing in the review. It is a good review. The parts not
built tonight are deferred on sequencing, not disagreement.

---

## §3 — What ships tonight

### A. The fast clock (done first — everything depends on it)
`HORIZONS = (1, 2, 5, 20, 60, 120, 252)`. Backward compatible: existing records
keep their own horizons; the tuple is only checked for membership. The short end
is **not** a licence to read a 1-day Brier as skill — one trading day is mostly
noise, so a 1d slice needs far larger n before it says anything. That is exactly
why it is useful: it accrues n fast. CANON §19 unchanged.

### B. P0 infrastructure
- Ledger moves under `DATA_DIR` with a one-time migration that refuses to
  overwrite a non-empty destination. ~87 real forecasts are at stake; losing
  them loses the entire forward calibration clock, so the migration's safety
  test is written before its code.
- `ledger_persistence` health check: if `AEGIS_DATA_DIR` is set and the ledger
  is not under it, DEGRADED with the reason named.
- Scheduler job-set canary: expected job ids declared in code, missing ones
  named in `degraded_reasons`. Detection only — auto-healing from a read path is
  a write from a read path.

### C. WHY-MOVED (the centrepiece)
Five stages, in order, each refusing to proceed on fabricated input:

1. **Deterministic attribution, no LLM.** Total P&L, per-position contribution,
   market/beta component, sector component, idiosyncratic residual. This is
   arithmetic and it is the ground truth the language model must explain. It
   still returns when DeepSeek is unavailable — an attribution with no
   hypotheses is a valid answer; a fabricated hypothesis is not.
2. **Seven independent specialists** (company_news, macro_rates, geopolitical,
   sector_factor, options_vol, revisions, adversarial skeptic), each called
   separately. A panel that agrees is one forecaster.
3. **Instant corroboration grading** — the fast clock. See §1.
4. **Forward claim mints a real `PredictionRecord`** through the existing spine.
5. **§20 batch self-check** — `effective_distinct_ideas`, because ten
   "independent" hypotheses that form one connected component have effective
   sample size one, and NIGHT-10 measured exactly that failure.

**Honesty constraints, non-negotiable:**
- Never assigns ground-truth cause. "What caused today's move" is not provable
  from one day. Two things are graded, both mechanical: was the stated
  cross-asset signature present, and did the forward claim resolve. Competing
  explanations are **preserved, not collapsed into a winner.**
- A hypothesis with no checkable corroboration and no forward claim is
  **rejected at parse time and counted.** That rejection count is the entire
  difference between this and commentary.
- Descriptive only. No buy/sell language.

### D. LLM telemetry
One provider-agnostic call ledger. The interesting bucket is not errors — it is
**calls that produced no gradeable output**, made a first-class number rather
than something you have to derive. Unknown model prices yield `None` and a
warning, never a silently-wrong zero that would read as "free" on every
dashboard.

### E. Research that runs while Murat is away
- **`WINNER-GENOME-1`** — pre-registered, then computed. The question is not
  "why did the winner win" but *which observable behaviours occur
  disproportionately among successful portfolios, survive controls for
  volatility and luck, and continue working in periods not used to discover
  them.* The core move is **separating selection from sizing**: run the same
  selections at 20% / 10% / 5% / inverse-vol / risk-parity / fractional-Kelly
  budgets. If high-dispersion selection is real but tournament sizing is
  suicidal, that is a finding, not a failure.
- **`THEME-CASCADE-1`** — pre-registered BEFORE looking at the second-wave
  names, so the SK Hynix / SanDisk / WDC / Kioxia / Vicor pattern cannot be
  retrofitted into evidence for itself.
- **`MODEL-ORCHESTRATOR-BENCH-1`** — see §5.

---

## §4 — The winner-selection problem, stated properly

Murat's instinct — *"it doesn't seem real, even looks like luck, but I don't
think so"* — deserves a precise answer, and the precise answer is **both**.

With ~2,600 teams, long-only, no leverage and a 20% position cap, the
leaderboard reports the **maximum of ~2,600 draws**. Under a null where every
team picks randomly among high-dispersion names, the maximum is enormous. A
+150% winner has an identical cousin at −60% that nobody interviewed. The RIT
captain said this outright: they optimised for being first, accepted they might
finish last, and led anyway.

That does **not** make the winners uninformative. It means the leaderboard
return decomposes into a **selection component** and a **risk-taking component**,
and only the first survives risk normalisation. The whole design of
`WINNER-GENOME-1` is to estimate that split rather than assume it either way.

The trap to avoid is the mirror image of Murat's suspicion: concluding "it's all
luck" is equally unearned. The null must be *simulated*, not asserted — which is
why the trial reconstructs the tournament with the real constraints and asks
whether a strategy family shifts the whole distribution upward or merely fattens
its right tail.

This connects directly to his own book. NIGHT-13 measured that his selection
added +20 to +43 points while his management subtracted 29 to 66. The Bloomberg
evidence says the same thing from the other direction: **the winning
architecture is not less risk, it is high-dispersion selection plus intelligent
execution plus adaptive sizing.** Three nights of results now point at
management rather than picks, and this trial tests whether that generalises
beyond one book.

---

## §5 — Fable vs Opus: what the benchmark can and cannot settle

Murat asked a fair question and deserves the limits stated with the answer.

**What is genuinely measurable tonight:** identical task set, identical starting
repo state, hidden acceptance checks written before either model runs, both
arms run as subagents from the same session, scored mechanically.

**What this design cannot settle, and no honest version of it could:**
- NIGHT-13 versus an Opus night is **not a comparison** — the tasks differed.
  Any claim built on that contrast is void, and the reviewer is right to say so.
- The DeepSeek dashboard measures downstream API spend, not orchestrator value.
- A benchmark of N tasks in one session estimates task-completion quality, not
  the thing Murat actually cares about, which is *whole-night autonomous
  research output*. That has a sample size of one night per model and no
  controlled version of it exists.
- Per-token prices quoted in the review are unverified here. Cost claims are
  reported as **token counts** plus a clearly-labelled price assumption, so the
  conclusion can be recomputed when the real rate is known.

So the deliverable is a **bounded** answer: per-task quality and defect-catch
rate at matched effort, with the honest note that the overnight-autonomy
question stays open. That is worth having. A confident ranking from this data
would not be.

---

## §6 — Standing rules that this night does not relax

More inference does not lower any bar.

- **§19** — every arm prints its own 80%-power MDE. A number below its MDE is
  not detectable and is never a kill. Thousands of new observations change the
  MDE; they do not change the rule.
- **§20** — batches are checked against themselves. Seven specialists agreeing
  is one specialist.
- **Deflation is cumulative.** Every trial registered tonight counts against
  every future promotion. The registry is not a trophy cabinet.
- **Fabrication and outcome-shopping stay refused** (NIGHT-13 ruling). The
  licensed substitute is the labelled ensemble.
- **A check that did not run is not a check that passed. A refusal is a
  finding.**
- **Descriptive until passed.** Nothing tonight ships buy/sell language.

---

## §7 — Do-nots for tonight specifically

1. Do not let the volume of API calls become the success metric. The metric is
   gradeable output per dollar, and a call producing no learning sample is a
   cost with no offsetting entry.
2. Do not collapse competing explanations into a single "cause." Preserving
   disagreement is the design.
3. Do not tune anything on the one war we know about. The exposure work already
   made this mistake's shape visible; GEO-1 must not repeat it.
4. Do not retrofit the second-wave names into evidence. Pre-register first.
5. Do not seed a shadow book unattended.
6. Do not report "live" on the strength of tests. Exercise the changed surface
   in production and read the content.

---

## §8 — End-of-night answers owed

1. Why the loop could not learn before, in one mechanical sentence, and what the
   grading latency is now.
2. What the deterministic attribution actually says about the day Murat asked
   about — the real numbers, per position.
3. Whether any specialist's cross-asset signature was actually present, with
   hit rates and counts, and how many hypotheses were rejected as ungradeable.
4. What `WINNER-GENOME-1` says about selection versus sizing, with the null
   simulated rather than asserted.
5. Fable vs Opus at matched effort — bounded, with the limits from §5 restated.
6. What is still owed, and what was deferred rather than done.
