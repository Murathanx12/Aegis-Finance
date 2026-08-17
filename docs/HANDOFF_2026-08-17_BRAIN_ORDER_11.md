# ORDER — brain → builder (order 11) — the start time, and the input it rests on

Binding. 51 unpushed on `aegis-finance`, 6 on the module, tree clean at
`fc59ac6`. Written 2026-08-17 ~12:55 local (04:55Z). **This order changes the
declared night start time and states why.**

---

## 0. My outer bound was wrong, and the way it was wrong is the finding

I have carried *"outer bound 20:20 local = 12:20 UTC"* in Orders 6, 7, 8, 9 and
10. I have never once run the guard against it. I ran it today:

```
start 12:20Z  arm_concurrency=1   REFUSED — NightWouldSpanTheOpen
                                  "the latest safe start is about 11:10Z"
start 12:20Z  arm_concurrency=2   PASS — headroom 0 minutes
start 12:20Z  arm_concurrency=5   PASS — headroom 0 minutes  (identical)
```

Three things fall out and the third is the one that matters.

**The 12:20Z bound is only reachable under concurrency**, and even there it
lands on **exactly zero minutes of headroom** — projected finish *equals* the
opening bell. That is not an outer bound with a margin; it is the point of
contamination, quoted for four days as though it were a safety limit.

**Concurrency ≥2 buys nothing over 2.** `conc=2` and `conc=5` return an
identical 70 minutes, because the model caps the speedup at a **declared
efficiency of 2.0**. Anyone reading "we run five arms concurrently" and
expecting five-fold would be wrong, and the receipt says `declared`.

**And `arm_concurrency` is supplied by the caller.** The guard's verdict is a
function of a number nobody has derived from the runner. A caller that passes
`arm_concurrency=2` against a serial runner receives `PASS` when the truth is a
69-minute overrun into the session. This is the standing rule landing on the
guard that protects tonight:

> **A guard whose input is on the honour system is not a guard — it will fool
> its own author.** It fooled me for four orders, in a document I wrote to stop
> exactly this.

**Do not fix it tonight.** A source edit on the critical path is the thing we
have refused all week, and `arm_concurrency` deriving itself from the runner is
a real change to a guard hours before the run it guards. The correct move costs
nothing:

> **Run the guard at `arm_concurrency=1` regardless of how the runner is
> configured, and choose a start time that passes serial.** A verdict that holds
> under the pessimistic branch does not depend on the unverified input at all.
> Then derive it properly after the push, with the missing-input refusal test.

---

## 1. The start time moves to 17:00 local (09:00Z)

Measured, `k=40`, `n_arms=5`, `arm_concurrency=1`, mean call 8.7s from Night 1's
own ledger, projection 139 minutes:

```
start (local / UTC)   headroom    tolerates a mean call of
15:00 / 07:00Z        251 min     24.4s     (2.8x the measured mean)
17:00 / 09:00Z        131 min     16.9s     (1.9x)   <-- ORDERED
18:00 / 10:00Z         71 min     13.1s     (1.5x)
18:30 / 10:30Z         41 min     11.2s     (1.3x)   <-- previously declared
19:10 / 19:10Z          1 min      8.8s     (1.01x)
```

**GPT's principle is right — *as late as reasonably safe, not as early as
technically possible*. It simply did not have the number that defines "safe".**
18:30 is not a compromise between freshness and margin; it is a **29% latency
overrun away from spilling into the session it forecasts**, on a one-attempt
paid run, where the failure mode is not "the night fails" but "the tool arms
read live intraday data while graded from a pre-open stamp" — hindsight handed
to the treatment arms of the primary contrast. A contaminated night is a total
loss of the attempt. Ninety minutes of pre-market news is a small power loss.
**Those are not the same size, and we do not get to re-run to find out.**

17:00 local keeps the trial's premise — 4.5 hours before the bell, US pre-market
open since 08:00Z, weekend news priced through the Asian session — and takes the
serial tolerance from 1.3× to 1.9×.

**Not earlier than 15:00 local.** Order 9's argument still binds in its real
form: the `A_snapshot` vs `B_tools` contrast pays the tool arms in *fresh
information*, so starting at the earliest legal moment pushes the primary
contrast toward the null for a reason unrelated to the hypothesis. Buying
headroom with freshness is a trade, and past 15:00 local it stops being worth it.

**The 45-minute freeze rule is unaffected and still binds.** `decision_ts` must
be within `MAX_DECISION_LAG_MINUTES = 45` of the *start*, not of the open.
Freeze the snapshot after 16:15 local, not before.

---

## 2. GPT's review — what it got right, and the two facts it did not have

It is a good review and its instincts are ours. **Its afternoon plan is already
spent:** N22, N23 and N24 ran and are committed at `fc59ac6`. It wrote two
conditionals and **both antecedents came back false**:

> *"If N22 says the risk outcome is confirmable and N24 says the return penalty
> can be bounded below the break-even, then we have something materially more
> interesting."*

N22 returned **0 of 8 cells resolvable at α 0.025 *and* 0.05** — `UNREACHABLE`,
not "not yet". N24 returned **`NOT_DEMONSTRATED` at the declared λ**, UCB(drag)
+2.93 against a break-even of 2.42 at λ=3, short by 0.51pp. So the tempering it
asks for is correct and **the real position is stronger than the caution it
wrote**: not *"promising, confirmation not yet established"* but *"screen-grade,
and this corpus cannot confirm it."* Say the second. It is the harder sentence
and it is the true one.

**Its one genuinely new contribution is worth taking.** Our 206-predictor sweep
charged a **flat 10bp**. Novy-Marx & Velikov's taxonomy is that **turnover is
the dividing line** — low-turnover anomalies survive costs at a very different
rate from high-turnover ones. A flat charge is therefore simultaneously too
harsh on the low-turnover survivors and too kind to the high-turnover ones, and
we already measured momentum's break-even at **2.6bp**, which says our own panel
knows this. **If it is a parameter swap — cost scaled by measured turnover, plus
a small grid rather than a point — run it in the remaining window. If it is a
project, it waits.** It can move which of the eleven survive in either
direction, and either direction is a result.

**Its citations are leads, not sources.** I have not read them and neither have
you. Two consequences, and the second is binding:

1. Nothing from that list enters a document as a citation until it is read.
   I could not verify the 2026 SSRN item exists at all.
2. **If Barroso & Detzel's "the managed *market* portfolio is the encouraging
   case" is part of why we ship a market-exposure product, that is R13f
   `hypothesis_source`,** and it caps the claim at
   `ADAPTIVE_HISTORICAL_VALIDATION`. External corroboration that arrives *after*
   we chose the configuration is free; external corroboration that *selects* the
   configuration is spent calendar. Declare which one it is before it is quoted.

Everything else it says — freeze the paid path, preflight the exact tree, leave
Railway and the quarantine until after the receipt, no new architecture — is
already standing and is reaffirmed here.

---

## 3. The window, in order

**Now → 16:00 local.** Offline only. The turnover-scaled cost sensitivity if it
is a swap. Documentation. **No edit to anything the night imports.**

**16:00.** Research changes stop. `git status` clean, and record the SHA the
night will run from.

**16:15–16:45.** Preflight from the exact tree and environment, verifying:
prereg hash · measurement-script hash · **the evidence population named in the
receipt** · information-cutoff semantics · read gate · same-40-names-per-arm
guard · credentials present and paid provider reachable · output directory
writable · spend ceiling armed *and* exercised · clock and timezone · no local
source mutation · no H1 read · receipt recovered from a synthetic zero-cost run.
**If something differs from the verified contract, do not improvise a fix at
16:50 — report it and hold.**

**~17:00 local (09:00Z). The night.** One attempt. Guard invoked at
`arm_concurrency=1`. If it refuses, **report the refusal and stop** — a refusal
is a finding, and there is headroom to 19:10 to decide calmly rather than at the
edge.

**After it, same evening:** campaign `--commit` (110/110/0) · `LIVE_FORWARD`
quarantine · `verify_before_push` **plus the module suite run directly** · push
51 + 6 · **verify production on the new commit**, deploy not CI.

**Then, and only then:** the pre-push sibling hole · `arm_concurrency` derived
rather than declared, with its missing-input refusal test · Railway sleeping by
receipt count over three days · the IIF-1 grader · `check_read` deriving
`n_graded_nights`.

---

## 4. Standing

- **A safety bound nobody has executed is a number, not a bound.** Quoting one
  for four days is how 12:20Z survived; running it took one command.
- **Where a guard's verdict depends on a declared input, invoke it at the
  pessimistic value** until the input is derived. A verdict that holds on the
  worst branch does not depend on the input.
- **Contamination and power loss are not the same size.** Trade freshness for
  headroom whenever the failure mode is total loss of a one-attempt run.
- **Corroboration that selects the configuration is `hypothesis_source`;**
  corroboration that arrives afterwards is free.

---

## 5. ADDENDUM (05:45Z) — your `.cache` defect has an app-side twin, on tonight's path

You found the shared store poisoning a *test*. I followed it into the *night*,
because the snapshot is built from the same store and nothing else this week is
on the critical path:

```
iif1_features.py:163  ->  data_fetcher.fetch_ticker_history
data_fetcher.py:96    ->  cache_get(key, _HIST_TTL)     _HIST_TTL  =    900s  (15 min)
data_fetcher.py:97    ->  cache_peek(key, _STALE_OK)    _STALE_OK  =  86400s  (24 h)
```

**The 15-minute TTL is fine** — well inside the 45-minute freshness rule, and I
checked the live store: 3 keys, one `tkr:hist10y`. Essentially cold. Not the
problem.

**The 24-hour stale-serve is the problem, and it is invisible three times over.**
On a throttle, `fetch_ticker_history` returns a copy up to a day old with the
same type and shape as a fresh one; `iif1_features` stamps it `fetched_at = now`
and `status = OK_DATA`; and `assert_decision_time_fresh` compares `decision_ts`
to the **wall clock, not to the age of the data behind it** — so the guard
passes on a snapshot that is a day stale. Worse, once `_trip_rl_breaker()` fires,
`_rl_breaker_active()` short-circuits **every subsequent name straight to stale
without attempting a fetch**. One throttle early in a 13–20 minute assembly of 40
names silently converts most of the snapshot. The only trace is a
`logger.warning`.

**No source edit — two procedural rules, both free:**

1. **After the snapshot is assembled and before the paid calls, grep the run log
   for `serving stale history` and for `RateLimited`. If either appears, the
   snapshot is contaminated: abort, re-freeze, restart.** This is why the start
   moved to 17:00 — there is now room to do that twice and still clear 19:10.
2. **Between the 16:00 freeze and the night, exercise no local endpoint.** The
   app still writes `<repo>/.cache` (correctly — you redirected the *tests*), so
   a local verification between freeze and run writes into the store the
   snapshot reads. That is your 422-became-200 defect pointed at the night
   instead of the suite.

**After the push:** `fetch_ticker_history` returns the served age, `FeatureValue`
carries it, and the receipt counts stale-served rows — so the contamination is a
number in the evidence rather than a line in a log. Same shape as
`arm_concurrency`: **derive what the guard checks, or refuse.**

— brain, 2026-08-17
