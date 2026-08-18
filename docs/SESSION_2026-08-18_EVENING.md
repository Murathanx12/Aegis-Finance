# 2026-08-18 evening — Night 2 launched; TAQ retires the band; two guards that could not have passed

Commits: `b470442` (+ this doc). Predecessors: `0bf4723` (Order 18 write-up),
`cace49e` (Amihud annotation).

---

## 1. Night 2 is running

Launched **16:57:31 local**, inside the derived 17:02 boundary. `--dry-run`
immediately before returned `READY TO LAUNCH` with **+6.5 min** margin; the
boundary was re-derived at launch time, never quoted from memory.

| | |
|---|---|
| run needs | 231 min `MEASURED_DURATION_BOUND` |
| assembly allowance | 36 min (worst measured 18.2 min × declared 2.0, cap 45) |
| latest safe RUN START | 17:39 local |
| latest safe LAUNCH | **17:02 local** — the one that binds |
| process | PID 51136 → venv re-exec 4312, single logical run |

**A relaunch, disclosed.** The first attempt piped the run through
`Tee-Object`. That is the canon defect verbatim — *a pipe discards the exit code
of the thing you are checking* — and PowerShell 5.1 additionally wraps every
stderr line of a native command as a `NativeCommandError`, so the run's own
failures would have been laundered into shell noise. Killed ~20s in, **verified
no snapshot and no receipt had been written**, relaunched with file redirection.
The check is the verification, not the intention.

**Finished 19:09 local, `status: ok`**, in 6,809s (113 min) against a 231-min
bound — 2,836 ledger calls, **600 records**, **120/120 cells paired, 0 dropped**,
0 cell failures on any of the five arms.

| | |
|---|---|
| spend | **$0.918462** (Night 1: $0.919725 — 0.14% apart, and both confirmed against the ledger directly rather than taken from the receipt) |
| decision lag | 18.61 min |
| tool-call drops | 2, all in `D_all`, reason `args_not_a_mapping` — recorded, not silently dropped |
| provenance | `9b2979b`, **`git_dirty: True`** |

The dirty stamp is expected and not a contamination: Order 19 ruled that the
freeze applies to the **frozen surface**, not the repo — main works through the
night, and the binding artefacts are the frozen feature snapshot, the 15
verified pre-registration fields, and the manifest's module hashes, none of
which moved. Both Fable and I were committing to main while it ran, which is
exactly the case that ruling anticipated.

**Naming defect, small but real:** `budget.measured_cost_night_1` holds
**tonight's** cost, not Night 1's — it is the latest measured night used as the
per-night planning rate, under a name that says otherwise. `projected_40_night_cost`
is that number × 40. Rename to carry the night it came from.

Two universe names 404 at yfinance — `MMC`, `PXD` (the latter genuinely
delisted, acquired 2024). Neither can pass the frozen `MIN_DOLLAR_VOLUME_20D`
filter without data, so the eligible population is unchanged by their absence;
noted as data quality, not a defect.

`llm_telemetry` warns of **2 unreadable ledger lines** on every read. This is
known, documented damage from LLM-SWARM-1 (two rows torn by interleaved appends
before the lock was added), and the instrument is behaving correctly by
downgrading spend and yield to LOWER BOUNDS. Not touched: modifying that module
while a paid run appends to the very ledger it writes is not a change to make
tonight.

---

## 2. The TAQ refusal was discharged by the thing it asked for

Order 18 §1 worded `calibrate_agk_against_taq`'s refusal as **"nobody has
tried"** rather than "we do not have TAQ", on the port-filtering lesson. The
check ran today: `taqm_2003..taqm_2026` + `taqmsec` entitled, verified by SELECT
probes rather than a catalogue read, direct port open. `TAQ_ENTITLEMENT` is now
`VERIFIED_2026-08-18` and the refusal is a build.

**Entitlement licenses nothing on its own.** It is a fact about a subscription;
a retired band is a fact about a *name*. `backend/services/taq_calibration.py`
retires the declared 1–5bp band **one name at a time** against a measurement,
with coverage gates (≥15 usable days, ≥5k quotes/day). An uncovered name keeps
its band **and the reason is recorded** — "TAQ did not cover it" and "TAQ
covered it and it was cheap" must never be the same row in a summary.

### A quantisation floor is a third kind of floor

The sweep established two: a constant offset is **BIAS** (subtract it), a
wandering null is **BLINDNESS** (replace the instrument — AGK's kind).

A quoted spread cannot be narrower than one tick. A name at a one-tick spread
reads one tick whatever the truth is. That is **QUANTISATION**: a hard UPPER
bound, with a **known sign**, that more data cannot tighten. Unlike blindness
the reading stays usable — an upper bound on a cost is exactly what a
conservative repricing wants — so such a name is **FLAGGED, not refused**. The
tick floor is DERIVED from the panel's own mid price, never declared.

### The sensitivity test refused the headline I was going to write

Three biases sit between a quoted NBBO spread and what a strategy pays, and
**their signs do not agree**:

| bias | sign |
|---|---|
| quoted, not effective | **OVER**-states |
| 09:45–15:45 time band | **UNDER**-states |
| message-weighted, not time-weighted | **UNDER**-states |

Two of three point DOWN, so `net_bias_sign()` is `NOT_ESTABLISHED`. "Quoted
over-states, so we are being conservative" is a sentence about one of the three.
`bias_ledger()` returns all three as data so a write-up cannot quietly carry
only the flattering one.

At the **declared 4× factor** (declared before it was applied), against AAPL's
0.485bp one-way (0.97bp full, halved):

| claim | arithmetic | verdict |
|---|---|---|
| below the band's **HIGH** end (5bp) | 0.485 × 4 = 1.94 | **HOLDS** |
| below the band's **LOW** end (1bp) | 0.485 × 4 = 1.94 | **FAILS**, breaks at 2.06× |

So what is established is that **the TOP of the declared band over-charges a
megacap**. Whether the truth is under the *bottom* of the band is a
point-estimate claim and the point estimate has an unresolved bias sign. The
AGK over-charge finding (15–20bp full read against 0.97bp measured) survives 4×
comfortably and is stated.

Lowering the factor to rescue the stronger sentence is exactly what declaring it
in advance exists to prevent. `test_the_sensitivity_SPLITS_two_claims_that_look_like_one_claim`
pins both outcomes.

**Scope.** AGK only resolves the wide end, so any overlap ratio belongs to that
end; `apply_calibration` **refuses outside the range it was measured on**.
Carrying it to a megacap is the original error wearing a correction.

### The panel landed, and it does not say what any of us said it said

180 tickers × 23 sessions (2026-07-15 → 08-14). `scripts/taq_calibrate.py` →
`docs/TAQ_COST_CALIBRATION.md`. **180 of 185 universe names retired their
declared band.**

**The band was a GOOD DECLARATION, not an over-charge.**

| where the panel sits vs the declared 1–5bp one-way band | names |
|---|---:|
| below it | 15 |
| **inside it** | **136** |
| above it | 29 |

Its midpoint is 3.0bp one-way; the panel's **median** retired name is
**2.732bp** — within **9%**. Order 18 declared 1–5bp before any of this was
measurable and **76% of the panel lands inside it**.

**Watch the unit.** 1–5bp *one-way* is **2–10bp full spread**. So "81 of 180
names sit below 5bp median spread" is a statement about the *full* spread —
2.5bp one-way, the lower-middle of the band, **not below it**. The panel's
p50 of 5.46bp full is 2.73bp one-way: dead centre. This is the same
full-vs-one-way confusion the `COST_BPS_ONE_WAY` type was introduced to stop,
arriving this time in the *interpretation* rather than the code.

My earlier framing on this page, and the framing in the handoff, both said the
band over-charges. That is true of the tight end and false of the typical name:

| claim, at the declared 4× | median name | survivors |
|---|---|---|
| below the band's HIGH end (5bp) | **FAILS** (breaks 1.83×) | 31 / 180 |
| below the band's LOW end (1bp) | **FAILS** (breaks 0.37×) | **1 / 180** |

I first had the script quote the **cheapest** retired name (IWM, 0.170bp),
which made both claims hold. That is picking the convenient end of a panel
exactly the way `resolve_band_by_picking` refuses to pick the convenient end of
a band, so it now quotes the **median** and prints both survivor counts.

**Denominator warning, and it could flip the page.** The band was declared for
the names AGK *cannot resolve* — the tight end — and these figures are computed
over the whole panel, because no per-name AGK reading is joined yet. Read every
count as "of all panel names", never as "of the segment the band was for".

**The tick floor binds at BOTH ends, for opposite reasons.** 27 of 180 names sit
at one tick: `IWM` 0.34bp at $295 (a penny is tiny) and `PLUG` 46.6bp at $2.14
(a penny is enormous). Same floor, opposite causes, both upper bounds.

### The panel is missing two names for a fixable reason

**TAQ's `sym_root` is capped at 4 characters** — probed directly: 8,717 distinct
4-char roots against **9** of length 5. The hyphen convention (`BRK-B` →
`BRK`+`B`) is a special case of that rule, not the rule. So `GOOGL` is
`GOOG`+`L` and `CMCSA` is `CMCS`+`A`, the pull asked for roots that do not
exist, and **got silence rather than an error**.

| absent | cause | remedy |
|---|---|---|
| `CMCSA`, `GOOGL` | **ACTIONABLE** — root/suffix mapping; the quotes are there (381,220 / 161,730 on 08-14, probed) | re-pull |
| `MMC`, `PXD`, `SQ` | **DELIBERATE/UNKNOWN** — dead or renamed (PXD delisted 2024; SQ now trades as `XYZ`, present under that ticker) | universe staleness, not a re-pull |

`taq_calibrate.py` exits **3** with a named canary while any actionable absence
remains, because the table is complete-*looking* either way.

**Resolved the same evening.** Fable re-pulled both (`9b2979b`), the canary
cleared to exit 0, and the numbers moved the way they should:

| | before | after |
|---|---:|---:|
| retired | 180 / 185 | **182 / 185** |
| below / **inside** / above the band | 15 / **136** / 29 | 16 / **137** / 29 |

`GOOGL` 1.234bp full (0.617 one-way, 4.29 ticks); `CMCSA` 4.118bp full
(2.059 one-way) and **exactly 1.00 ticks** — another quantisation-floor name.
Only the three genuinely dead tickers remain absent.

---

## 3. The launcher's acceptance test could never have passed

The first genuinely scheduled firing wrote itself at **17:00:01 local**
(`iif1_launches/2026-08-18.2.json`). Every derived check passed. Verdict
`REFUSED` for `NOT_ARMED` only — correct. And:

```
"invocation_mode": "scheduled",  "stdin_isatty": true,  "contradicted": true
```

`AegisIIF1NightLauncher` is registered **`LogonType: Interactive`**, so it runs
inside the logged-on session *with a console* and its stdin **is** a terminal.
`observe_invocation`'s docstring asserted the opposite — "a Windows scheduled
task runs with no console attached" — which is true of S4U and **false for this
registration**.

Consequence: every future firing would have been disqualified identically. 3/3
could never accumulate. `n_consecutive` would have read 0 on Wednesday,
Thursday and Friday, and the discovery would have landed **on the morning
arming was meant to happen**.

**A refusing guard and a dead job produce identical silence.**
`acceptance_report` now separates them:

| situation | verdict |
|---|---|
| nothing has fired | `NOT_ACCEPTED` — waiting is the remedy |
| firings on record, **every one disqualified** | `UNSATISFIABLE_IN_THIS_ENVIRONMENT` |
| 3 consecutive clean scheduled receipts | `ACCEPTED` |

`accepted` stays False in all but the third — this buys the *warning*, not the
arming. **The contradiction test is not relaxed**: it is reading its input
correctly and its input is confounded. A new test asserts **all three verdicts
are reachable**, because adding an unenterable branch to fix an unenterable
branch is the same mistake with fresh paint.

The code declares unsatisfiable at n=1 deliberately — the confound is
structural, not stochastic, and waiting for three costs the whole warning. The
registration was confirmed directly with `Get-ScheduledTask`, so for *this*
environment the diagnosis is verified, not inferred.

### Attended, for Murat — Friday's arming depends on it

Both remedies change the registered task, which is why neither was done here:

```
# preferred: remove the confound, keep the honest detector
schtasks /Change /TN AegisIIF1NightLauncher /TR "cmd /c cd /d C:\Users\mrthn\aegis-finance && python -m scripts.run_night_launcher --scheduled < NUL >> C:\Users\mrthn\aegis-finance\backend\data\optimus\launcher.log 2>&1"

# alternative: re-register S4U ("run whether user is logged on or not")
```

The 3/3 receipt clock **restarts from the first clean receipt**, so Friday's
arming is not achievable if this is fixed after Thursday. `LastTaskResult: 0`
and `LastRunTime 17:00:00` confirm the task itself fires correctly — the
registration is right about *when*, wrong about *how*.

---

## 4. The gate's own process check had never looked

`verify_before_push` step 2 printed **"competing python processes: 0"** for
weeks. It needs `psutil`; `psutil` is not installed on this machine; the
`ImportError` branch returned `[]`. **Zero is exactly what a clean machine looks
like**, so the diagnostic printed the all-clear without ever looking — found
today while an IIF-1 night run and four MCP servers were demonstrably alive.

Now: a stdlib Windows fallback, and `None` → printed as **`UNKNOWN — could not
look`** when it genuinely cannot. *"We did not look" must not read the same as
"we looked and there was nothing"* — the same rule already written into
`stdin_isatty` two hundred lines away in the launcher, which is where the shape
was recognised.

The gate run for this very commit reports **8**, including the Night 2 process.

---

## Verification

| | |
|---|---|
| gate | 4938 passed, 22 skipped, exit 0, tree stable |
| CI | `b470442` |
| prod | **no router or `main.py` imports** `cost_model`, `taq_calibration` or `night_launcher` — a skipped Railway build is correct; nothing prod serves changed |

## Open

* The TAQ panel has not landed; `scripts/taq_calibrate.py` refuses until it does.
* The AGK↔TAQ overlap is not computed (needs OHLC bars per name — a network
  fetch, deliberately not run against the same machine as a paid night).
* Effective spread still needs the trade-quote join; nothing may carry
  `MEASURED_TAQ` until it exists, only `MEASURED_TAQ_QUOTED`.
* The prod-monitor email fix has still not fired in production — its window
  opens 19:00 local.
* Launcher arming blocked on the schtask remedy above.
