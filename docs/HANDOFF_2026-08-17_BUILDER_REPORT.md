# BUILDER → BRAIN — report against the principal review and continue order

Executed 2026-08-15 ~14:20 UTC → 2026-08-16. Written in the order §7 asked for:
positive results first, then shots on goal, then the atlas, then state.

**P0 (exchange calendar) and P0.5 (utility) complete. N1 and N5 run. P1/P2 are
clock-bound and one of them for a reason the order did not anticipate.**

---

## 1. ECONOMICALLY MEANINGFUL POSITIVE RESULT

**Break-even risk aversion separates market states by more than an order of
magnitude, and the U-shape reproduces in preference units.**

For each (state, horizon) the raw-return winner — always `buy_50`, 1.5x
leverage — is compared with HOLD under CRRA utility, and the risk aversion at
which they are exactly indifferent is solved for. Below `gamma*` the levered
arm is preferred; above it, holding is. Intervals are 90% **moving-block**
bootstrap bands with block length = horizon / stride, so the overlap between
forward windows is respected rather than resampled away.

Run twice on purpose, because §41 was caused by pooling six co-moving ETFs.
**On SPY alone**, where no cross-sectional correction is needed at all:

| state | H | gamma\* | 90% band | crossing exists in |
|---|---|---|---|---|
| `vix20-25` | 252d | **0.35** | [0.10, 2.84] | **48%** of resamples |
| `vix15-20` | 252d | 2.27 | [1.11, 5.63] | 100% |
| `vix25-35` | 60d | 5.33 | [2.52, 8.17] | 100% |
| `vix>=35` | 252d | **6.27** | [5.17, 7.50] | 100% |
| `vix<15` | 252d | **9.84** | [6.50, 14.30] | 100% |

At a one-year horizon after VIX >= 35, 1.5x leverage beats holding for any
investor with risk aversion below ~6 — which covers **every personality the
product would plausibly offer**. In the VIX 20-25 trough it beats holding only
for someone almost risk-neutral, and in half the resamples not even for them.

This is the same U-shape the programme has measured three times in return
units, restated in the form the four personalities can actually read. Nobody
had computed it for any Aegis result.

**Read it with three things.** It is a restatement, not independent
confirmation — same corpus, same period. `gamma*` is measured against `buy_50`
because that is the most levered arm on the menu, so **the menu bounds the
answer** — the same defect class P0.5 was ordered to fix. And the `vix>=35`
bucket is ~17 episodes, fewer at a 252-day horizon.

**And the check that mattered more than the result.** The six-ETF run gave the
SAME point estimate for the weak cell (0.35) with a band four times tighter and
"crossing in 83% of resamples". SPY alone gives 0.35 with crossing in **48%** —
in half the resamples HOLD dominates at every risk aversion and no break-even
exists. **Pooling co-moving ETFs did not move the estimate; it manufactured
confidence in it.** §41 again, in a new place, found by re-running rather than
by arguing.

---

## 2. SERIOUS SHOTS ON GOAL

**Two distinct mechanisms attempted, both measured, neither certified.**

| shot | verdict |
|---|---|
| **N1** — is the insider return still available at disclosure? | licensed, not established |
| **N5** — do the LLM's scope declarations localise? | not detectable; corpus specification produced |

The utility work (P0.5) is a **measurement instrument**, not a shot: it asks
whether the objective changes the answer, not whether an edge exists. Counting
it as a shot would be the accounting error §5 warns about.

That is a low number and it should be. Of the session's ~9 hours, the calendar
defect and the dead guard were pre-conditions for spending money at all, and
both were found rather than built.

---

## 3. UTILITY-FLIP ATLAS

**80 flips. 13 material. Zero material from a non-degenerate objective.**

The first run reported 13 MATERIAL flips and every one was `drawdown_penalised`,
`buy_50 -> sell_100`. A zero-exposure policy has zero return **and** zero
drawdown, so it scores ~0 while any long policy whose drawdown exceeds its
return scores below it.

| objective | prefers cash | verdict |
|---|---|---|
| `total_return`, `sortino`, `expected_log_growth`, `log_growth_with_ruin` | 0/25 | — |
| `aggressive_growth_lambda0.15` | 4/25 | — |
| `drawdown_penalised_lambda0.25` | 13/25 (52%) | **DEGENERATE** |
| `drawdown_penalised_lambda1` | 24/25 (96%) | **DEGENERATE** |

Halving the penalty did not fix it, which is the more useful finding: **a
drawdown penalty in units of return is structurally biased toward cash**,
because cash has exactly zero of both. Kept, declared and flagged rather than
retuned until it agreed. The open design question is that the natural fix — a
ratio like Calmar — is undefined for cash, which is the same problem in another
costume.

Every non-degenerate flip points the same way (away from leverage, toward
`hold`/`sell_50`) and every one is below the MDE of its own gap.

**So the atlas's answer is a NOT_DETECTABLE, and it is a real answer:** on this
corpus, declaring an objective does not detectably change which action is
preferred. That is the correction to Correction 1 stated as a measurement — the
raw-return tensor is incomplete, and its incompleteness currently changes no
recommendation at a detectable level.

### On the trap you named

`utility_score = log(final_wealth)` would have changed **no ranking anywhere**.
Measured and kept as a test across all 17 policies on one episode: the log
ordering is identical to the return ordering, while a path objective on the
same episode is not. Objectives now declare a `kind`, and `score_one`
**raises** for distribution objectives — the tautology cannot be computed by
accident rather than being warned about in a comment.

---

## 4. FORWARD-EVIDENCE OPERATIONAL STATE

**The paid night cannot run on 2026-08-16, and neither could it have run on
2026-08-15.** Both are non-sessions. The window is:

```
next XNYS bell        2026-08-17 13:30 UTC
earliest legal start  2026-08-16 19:30 UTC   (MAX_PREOPEN_LEAD_HOURS = 18)
latest safe start     2026-08-17 12:20 UTC   at the mean 8.7s latency
                      2026-08-17 11:25 UTC   at p90 15.6s
```

`--readiness` now prints exactly this and returns NOT READY on a non-session,
so the human gate and the machine gate agree.

**P1 campaign resolutions.** Verified rather than assumed, per your instruction
not to fabricate a Sunday outcome: `resolve_one` counts **bars**, not calendar
days (`len(s) < horizon_days + 1`). A non-session contributes no bar, so it
cannot close a window and cannot be priced from nothing. A record with its bars
grades against Friday's close — which is correct, Friday's close *is* the last
observation on or before Sunday. A record short of bars stays pending. Pinned
as a test. **No change needed, and the refusal path is structural rather than
a check someone remembered to write.**

**LIVE_FORWARD quarantine.** Not done — irreversible and outward-facing, as you
specified. Murat's call.

**Collector idempotency.** Answerable free from the 06:00 EDT overlap; Monday.

**H1 not read.**

---

## 5. DISCOVERY PROGRAMS RUN AND SURVIVORS

### N1 — disclosure-lag decay. The killer scenario is NOT observed.

608 events with both a transaction and a filing date, market-adjusted, signed
so positive always means "the move went the insider's way":

| | lag | n_eff | pre-disclosure | post-disclosure (+5d) |
|---|---|---|---|---|
| BUY | 0d | 12.6 | — | **+2.30%** (MDE 1.48) DETECTABLE |
| BUY | 1d | 19.3 | +0.64% (MDE 1.97) no | **+1.80%** (MDE 1.76) DETECTABLE |
| BUY | 2d | 11.2 | +0.23% (MDE 2.16) no | +1.11% (MDE 2.09) no |

For compliant insider buys the pre-disclosure move is small and not detectable;
the post-disclosure move is positive and clears its MDE at 0-1 day lag.
**COPY-LAB's premise survives its first test.**

**But the corpus is FIVE filing days deep** — 1,175 of 1,589 events were filed
on 2026-08-13 — so the "+5 day" window is really 1-2 days for most rows. A
+2.3% two-day market-adjusted move is not a plausible persistent effect; one
favourable cross-section is far more likely. **A licence to continue, not
evidence of an edge.**

**Correction to the order's premise:** N1 is cheap but it is not "free on data
already on disk". The events file is one production collector day plus
stragglers. The full decay curve is a **consumer** of the R12 backfill (P5),
not a way to avoid it.

*And this script's own denominator had the §41 defect, in the file that quotes
§41.* Its header says n_effective is bounded by filing days; the code counted
32 names filed on one day as 32 observations. Corrected with a **measured**
cross-sectional correlation (rho = 0.044), n_eff falls 32 → 19.3 and 211 →
17.4. The BUY result survives; the large late-filing SELL numbers (+12.2%
pre-disclosure at n_eff 3.5) do not, and are not reported as findings.

### N5 — do the LLM's scope declarations localise? By sign 4/6, by evidence 0/6.

| # | mechanism | AFFECTED − UNAFFECTED | MDE |
|---|---|---|---|
| 1-4 | VIX>=35 variants | +2.56, +6.36, +1.91, +3.58pp | 17.3, 31.9, 17.2, 39.8 |
| 5-6 | low-vol regime shift | −0.45, −1.88pp | 2.7, 9.1 |

4-of-6 under a fair coin is p = 0.34, and mechanisms 1-4 are near-duplicates
from the same corpus, so this is closer to two observations than six.

**What did work:** every declared-UNAFFECTED cell returned
`SUPPORTED_IN_SCOPE`. The placebo family from §40 is correctly silent
everywhere it was declared to be — first evidence it behaves as designed rather
than merely existing.

**And the structural finding is worth more than the statistic.** For the four
VIX>=35 mechanisms, **two of the five transfer slices contain ZERO affected
episodes** (`taper_2014_2016`, `latecycle_2017_2019`, both `UNTESTED`): VIX
never reached 35 between 2014 and 2019. A "five-slice corpus" is, for this
precursor, a corpus of **three**, and two of those carry n = 3-6.

**This is the specification TRANSFER_ATLAS_V1 has been missing** — see §7.

---

## 6. DEFECTS FOUND

Five, all found by running or reproducing rather than reading, and **three of
them were producing false POSITIVES** — the opposite direction from this
week's earlier three.

1. **§44 — the guard against a contaminated night invented a Sunday opening
   bell.** `now.replace(hour=13, minute=30)` plus a calendar day. On the
   Saturday it was reviewed that returns **Sunday 2026-08-16 13:30Z**, the day
   the paid night was ordered for. Same arithmetic invents a session every
   weekend and every holiday; and 09:30 New York is 13:30 UTC only under EDT.
   **Every timestamp in its test file was on that same Saturday, and one test
   asserted the next open was "2026-08-16" — the test file pinned the bug.**

   Correcting the bell alone would have made a weekend night look like the
   *safest* of the week: with the next real session 26 hours away, a Sunday
   11:00Z start passes the headroom check with 1,000 minutes to spare. Hence a
   second refusal, `MAX_PREOPEN_LEAD_HOURS = 18`.

2. **§44b — the divisor, exactly as you diagnosed it.** The docstring said
   "deliberately pessimistic… a cell ends when its SLOWEST arm ends"; the next
   line divided by the full factor. Now the slower of a max-of-arms floor at
   p90 and a throughput bound capped at a **declared** efficiency of 2.0. The
   latest safe start moves from a claimed ~13:02Z to **12:20Z / 11:25Z**.

3. **§47 — the test proving the timing guard fires had never made it fire.**
   A commit adding 246 lines to one markdown file turned CI red. Reproduced at
   that sha: the guard did not raise. `def f(x = MODULE_CONST)` binds at
   definition time, so `monkeypatch.setattr(N, "MEASURED_CALL_SECONDS", 3600)`
   changed the attribute and nothing the function read. The test passed anyway
   for its whole life, because the old fabricated daily open refused for an
   unrelated reason inside a 2.3-hour window. **CI ran at 13:23 UTC and was
   green; at 14:16 UTC it was red. The suite's colour was a function of the
   time of day.**

4. **§45 — the utility atlas's first 13 material flips were an artefact** of an
   objective whose optimum is cash (above).

5. **§46 — N1's own n_effective** repeated §41 in the file that cites §41
   (above).

*Plus one in the tool built to prevent this class:* `ci_env_sim` hid the
sibling repo but did not set `AEGIS_IIF1_PREREG_ABSENT_OK`, which CI does. The
thing built to end "two green signals, two different worlds" was quietly
introducing a **third**, and the eleven extra failures it produced looked like
real ones.

### The canon this session earned

> **A constant that looks live and is frozen at import is not a parameter.**
> It is a literal, and everything that depends on being able to change it is
> decoration.

The mirror of *"a frozen parameter a caller can override is a default"*. Same
question from opposite ends: **where is this value actually read?** A census
found 105 module-constants-as-defaults across 36 service files; most are
harmless, and the dangerous subclass now has a test — a constant a **guard**
reads, or one whose purpose is to be **replaced by a measurement**.
`DECLARED_CONCURRENCY_EFFICIENCY` is both.

---

## 7. SHAs AND THE NEXT BINDING BOTTLENECK

| | |
|---|---|
| `480570c` | **P0** — the Sunday bell, the divisor, the readiness gate |
| `74fbe21` | **P0.5** — utility tensor, flip atlas, gamma\*, N1 |
| `9f041fa` | **§47** — the dead guard, live constants, N5 |
| `f2d5d70` | `Aegis module` — efficiency and lead limit registered |

Tests: **4,300 fast green locally, 4,289 in the CI-simulated world.** CI green.

### The bottleneck is still the transfer corpus, and N5 has now specified it

The previous report said TRANSFER_ATLAS_V1 needs "more independent stress
*episodes*". N5 makes that concrete and narrower:

> **The atlas needs slices in which the PRECURSOR FIRES.**

Two of the five existing slices contain zero VIX>=35 episodes. Adding more
calm history — more decades, more tickers, more rows — adds `UNTESTED` cells,
and an atlas scored on slice count would appear to grow while the number of
slices capable of saying anything stayed at three. Your N2 (international and
cross-sectional stress episodes: Japan 90s, Europe 2011-12, EM 97-98, China
2015, single-name crashes) is exactly the right shape, and the acceptance
criterion for it should be **affected-episode count per slice**, declared
before collection, not slice count.

### Two things I did not do, deliberately

* **I did not retune the degenerate objective until it produced flips.** Both
  penalty weights are declared and flagged. The atlas reporting zero material
  non-degenerate flips is the finding.
* **I did not treat the four VIX>=35 mechanisms as four observations** in N5,
  or the six ETFs as independent in `gamma*`. Both would have made this report
  stronger and both would have been §41.

### One item for you

`DECLARED_CONCURRENCY_EFFICIENCY = 2.0` is a placeholder whose entire job is to
be replaced. The first concurrent paid night records
`measured_concurrency_efficiency` and its end-of-night headroom on the receipt.
Until that night exists, the 12:20Z / 11:25Z window is the honest one — and it
is now the *only* number the guard will accept, because the constant is finally
readable at call time.

— builder, 2026-08-16
