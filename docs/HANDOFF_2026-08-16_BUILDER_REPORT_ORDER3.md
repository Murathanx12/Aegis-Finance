# BUILDER → BRAIN — against order 3 and the principal review

Executed 2026-08-16, ~13:40 → 15:00 UTC+8. Written in the order the review's
"Next handoff" section asked for. **$0.00 spent.**

---

## 1. ECONOMICALLY MEANINGFUL POSITIVE FINDINGS

### 1a. The precursor library is REFUTED as a de-risking trigger — a real negative, not a failed detection

The review demanded an equivalence test against an economically chosen margin
rather than a below-MDE null reported as an absence. Running one produced a
**stronger** result than either the original claim or its correction.

The library's only declared action is cutting exposure when a precursor fires.
With `q = 0.10` fixed by construction, Bayes gives the precision directly —
`P(tail | fire) = L × q`, so a lift of L means the warning is right `10L`% of
the time — and de-risking pays when `L·q·|μ_tail| > (1−L·q)·μ_rest + cost`:

```
L_min = (μ_rest + cost) / ( q · (|μ_tail| + μ_rest) )
```

`μ_tail` and `μ_rest` are properties of the unconditional return distribution.
Nothing the test discovers can move them. That is what makes the margin
prospective in the only sense that matters.

| H | tail | lift | precision | upper 95% bound | break-even `L_min` | verdict |
|---|---|---|---|---|---|---|
| 20d | bottom | 0.954 | 9.5% | **1.257** | **1.69** | **`RULED_OUT`** |
| 60d | bottom | 0.808 | 8.1% | **1.234** | **2.11** | **`RULED_OUT`** |

Stable across all nine cost × block-length combinations. **When a precursor
fires, a bottom-decile move follows 9.5% of the time; break-even is 16.9%.** Not
a weak signal — the wrong side of the line, with the interval's upper bound
still short of it.

`REFUTED_IN_SCOPE`, and it closes exactly one thing: the six-rule library as a
de-risking trigger. Not the mechanisms individually, not other actions, not the
85% it never marked.

### 1b. The grammar CAN mark the moves the library misses — confirmed out of sample at p = 0.015

Before paying for LLM autopsies, the free question: an autopsy's output must
compile into the eight-feature transferable vocabulary or be refused at the
door, so **does any rule in that vocabulary mark the uncovered moves?**

13,728 candidates. Train `SPY/XLF/XLE` pre-2016, foreign `QQQ/IWM/XLK`
post-2016, confirmation `DIA/XLV/XLI/XLP/XLU/XLB` declared in a prereg amendment
before being touched. Bar inherited from 1a, not invented.

| H | train pass | foreign median lift | aggregate foreign | **confirmation** |
|---|---|---|---|---|
| 20d | 582 / 13,728 | 1.51 (p90 2.43) | 1.513 vs placebo 1.011, p = 0.015 | **1.271 vs 0.905, p = 0.015** |
| 60d | 276 / 13,728 | 0.91 | 0.905 vs 0.844, p = 0.428 | 1.330, p = 0.075 |

**H0 refuted at 20 days.** Effect decays monotonically as it should — ≥1.69
selected on train, 1.513 foreign, **1.271 confirmation**, the last being the
unbiased one.

### 1c. Vol-targeted sizing: the fourth convergent finding, built

At **matched ex-post realised volatility** (because vol targeting lowers average
exposure, and quoting either raw number alone chooses the answer):

* growth better in **3/4**, drawdown better in **3/4**, mean **−6.87pp**
* `vol_target_2x`: drawdown better in **4/4**, mean **−10.54pp**
* **QQQ buy-and-hold hits the ruin floor at −83%. Every vol-targeted variant
  does not.**

---

## 2. NEW INVESTMENT CANDIDATES

**ZERO.**

1a is a negative. 1b is confirmed at lift 1.271 and **1.271 is below the 1.69
break-even** — the set marks uncovered moves better than chance and still does
not mark them well enough to pay for the trade it implies. 1c is a
`PRODUCT_EXPERIMENT` whose primary metric is `NOT_DETECTABLE_IN_SCOPE`.

The categories stay separate, per review §12: **three scientific findings, one
product decision, zero investment candidates.**

---

## 3. SERIOUS SHOTS ON GOAL

Six, all pre-registered before the statistic existed: **N4B** (equivalence),
**N9** + amendment (grammar search + confirmation), **N12** (sizing),
**N11/RISK-RESIDUAL-1 stage 1** (baseline ladder), **N1/N13** (disclosure lag),
**R13** (a guard, not a hypothesis).

Distinct mechanism families: still small. §5's `WINNER_MATCHED_LOSER_FACTORY_V1`
was **not built** — see §10.

---

## 4. CAMPAIGN-FORWARD RESOLUTION

**Dry run re-verified, `--commit` NOT run. It is your keystroke.**

```
real ledger    backend/data/optimus/predictions.jsonl
sha256 BEFORE  ff458c779830c57751c1ca1b30f49dc1b8e7e392c69ee9461f9d6d0d986dccb9
due            110      would resolve 110      unpriceable 0
still pending  19,957   overdue after 0        health after: ok
priced from    fresh_fetch
sha256 AFTER   ff458c77…  UNCHANGED — the production ledger was never written to
```

`python -m scripts.resolve_campaign_ledger --commit`

**And the operation is now provably isolated from production.** See §5.

---

## 5. THE LEDGER VOLUME QUESTION — CLOSED, and it was a misreading

The review blocked the quarantine until the mount behaviour was reconstructed.
Deployment `7e2bbe35` spans both boots and its own logs settle it:

```
Mounting volume on: .../bind-mounts/9fe74ada-…/vol_ejglke5as9a86nhc
2026-08-15 17:42:46  Prediction-ledger persistence: {'dest_dir': '/data/optimus',
                     'legacy_records': 20073, 'dest_records': 112, …}

Mounting volume on: .../bind-mounts/9fe74ada-…/vol_ejglke5as9a86nhc
2026-08-16 02:06:29  Prediction-ledger persistence: {'dest_dir': '/data/optimus',
                     'legacy_records': 20073, 'dest_records': 112, …}
```

**Byte-identical. Same volume, same mount, both numbers printed a few
characters apart at every boot.** No mount ever changed; the "02:06 boot saw
20,073" was the in-image campaign file being read off the same log line as the
volume's 112. `evidence_population.ledger_dir()` routes the two populations to
two paths deliberately, with the reason in the code.

Consequence for §4: the resolver writes the repo file, production reads the
volume, and the migration will not copy into a non-empty destination. **The two
operations cannot contaminate each other, by construction and now by receipt.**

The quarantine's blocker is cleared. It remains attended and irreversible, and
what it should do is now exactly specified (`docs/LEDGER_VOLUME_RECONSTRUCTION_2026-08-16.md`).

**One thing to look at before the paid night:** four container restarts in under
four hours (02:06, 04:36, 05:40, 05:59 UTC). No data lost — the volume is doing
its job — but a service restarting that often is worth a glance before a
one-attempt paid run is pointed at it.

---

## 6. §56 — VERIFIED LIVE, not simulated

Prod at `8c57800`, on a restart into a cache warmed at the 04:36 boot:

```
status ok · fetch_passes 1 · served_from_cache True
served_fetch_at 2026-08-16T04:36:10+00:00 · served_age_hours 1.44
19 FRESH · 4 STALE_USABLE · degraded_reasons []
```

The original fetch time survives the restart; `fetch_passes: 1` is the
deliberate floor that lets `degraded_reasons` still name a critical gap. All
seven items on the review's list check out; the one that cannot be shown live
without breaking production (a critical series frozen missing into the cache) is
the pre-existing unit test. **One new test pins the whole payload shape
together, because the fields lie separately.** Then stopped, as ordered.

---

## 7. RISK-RESIDUAL-1 — the baseline ladder, and N11's premise refuted

Five rungs on identical embargoed folds, fitted rungs fitted on train only:
rv20, EWMA(0.94), HAR, Log-HAR, the N6 14-feature model. Twelve securities.

**At 20 days: 0.6096 / 0.6143 / 0.6120 / 0.6140, with paired MDEs of 0.005 to
0.010.** The comparison is *well powered* — rungs that are nearly the same model
vary together fold to fold — and they are still indistinguishable. **This is a
powered null, not a failure to detect.** EWMA wins at 5d and 20d, Log-HAR at
60d, by margins nobody could trade.

The ML model adds **+0.0240 against MDE 0.0716**. Not detectable, and the MDE is
fourteen times the gap between the cheap rungs because the model is the volatile
one across folds.

**And N11's premise is false.** The four slices were declared before the numbers
as "where trailing vol breaks":

| slice | best-cheap IC | vs unconditional 0.614 |
|---|---|---|
| regime_transition | 0.633 | **higher** |
| vol_of_vol | 0.652 | **higher** |
| stale_window | 0.594 | lower |
| post_shock | 0.588 | lower |

**Volatility is MORE predictable at regime transitions and high vol-of-vol, not
less.** The model does not detectably win in any of the four. The
"wins-where-the-baseline-breaks" hypothesis is not supported, and two of the
four places it was supposed to break are where everything works best.

**Stated in the output, not the footnotes: the ladder has no implied-volatility
rung.** No OptionMetrics licence, no point-in-time surface. Every conclusion
here is about the *realised*-vol ladder — which is exactly where the residual
information is least likely to be hiding.

---

## 8. N1 / N13 — the disclosure-lag kill did NOT fire

Ordered highest-EV twice, skipped twice. It runs in four minutes. The
reconstructable reason it was skipped: the corpus is **five distinct filing
days** deep, and that was read as "not worth running yet". Wrong — five days is
enough to learn that the kill does not fire.

608 events, 193 tickers. The two tables invited the same §18 error this session
spent the morning correcting, so the script now computes the quantity COPY-LAB
turns on — **pre minus post, paired within event**:

| action | lag | n | diff (pre−post) | MDE | |
|---|---|---|---|---|---|
| BUY | 1d | 35 | **−1.17pp** | 2.96 | not detectable |
| BUY | 2d | 30 | **−0.88pp** | 2.22 | not detectable |
| SELL | 6-10d | 50 | +15.72pp | 7.70 | DETECTABLE — but 50 names on **one** filing day, n_eff 3.5 |

`NOT_DETECTABLE_IN_SCOPE`. **COPY-LAB is not terminated.** The binding
constraint is collection cadence, not event supply — and under R14 that is a
fixable constraint, unlike twenty-five crisis episodes.

---

## 9. VERDICT CORRECTIONS AND DEFECTS

`docs/VERDICT_CORRECTIONS_2026-08-16.md`. Four corrections; one of them was not
a reporting slip.

* **D4 → `NOT_DETECTABLE_IN_SCOPE`.** Its prereg says so in as many words;
  every difference is under a seventh of its MDE. `n6_moments.py:341` prints
  exactly that verdict — **the code obeyed the protocol and the summary did
  not.** Cheap kills 2 → 1.
* **N6's rv20 MDEs existed and were dropped.** "At sixty days it is materially
  worse" describes the *least* detectable cell in the table (−0.085 against MDE
  0.180, 47%). "Do not expect ML to add" deleted.
* **N6's comparative claim scoped** (§18; AUC and Spearman IC are not on a
  common scale, so the point estimates cannot be differenced at all).
* **N4's "NO COVERAGE" was compiled in** — the literal string emitted by
  `n4_precursor_coverage.py:207` whenever `|lift−1| < MDE`, running on every
  atlas run. Now `NOT DEMONSTRATED`.

**Defects: 2 → 3.** New instruments this session: `power.can_rule_out_at_least`
(the test a null owes before it may be called a negative), and R13.

### R13, built and verified end to end

`event_frequency_per_year` + `declared_effect_size` + `outcome_dispersion` are
required prereg fields; `lint_prereg` refuses a pair N8's curve cannot resolve,
and names the smallest effect that *would* be registrable. Three things worth
their own line:

* it runs **before** the corpse verdict — an unresolvable design is not improved
  by being novel, and printing PASS first is how it gets registered anyway;
* an unfilled placeholder must not parse (`<e.g. 10pp>` contains a number, and a
  parser that reads it clears every copy of the template);
* **the exit code IS the guard.** `lint_prereg` returned 1 only on `BLOCKED`, so
  both R13 refusals would have printed and exited 0. Caught by running it.

Verified: the crisis claim the programme kept registering (0.7/yr, 3pp, crisis
dispersion) is refused with `n_required 273` against `n_available 25` and a
floor of **9.9pp** — N8's curve, reproduced by the gate that enforces it.

### The process correction (§15)

`scripts/verify_before_push.py`. Five checks; the one that matters is #4 — every
tracked file hashed before and after the suite, and **a tree that moved during
the run DISCARDS the result** rather than reporting it.

It fired on its own first real run, named nothing, and I could not act on it.
Hashes are per-file now and it prints which paths moved. **On re-run it passed
with no files listed, so the original trip did not reproduce and I do not know
what caused it** — recorded rather than explained away.

---

## 10. WHAT WAS ORDERED AND NOT DONE

Named plainly, because scaling the work down is not my call:

* **§5 `WINNER_MATCHED_LOSER_FACTORY_V1`** — not built. The largest gap in this
  report. N9 attacks coverage from the grammar side; the factory attacks it from
  the episode side and is the bigger of the two.
* **§7 `SEMANTIC-IMPLIED-DISAGREEMENT-1`**, **§8 `TAIL-GRAPH-1`**,
  **§9 `LLM-UNCERTAINTY-1`**, **§10 `VALUE-OF-INFORMATION-AGENT-1`**,
  **§11 mechanismized reflection** — none started.
* **§13 minimum effect of interest from economics** — done for *one* mechanism
  family (N4B's `L_min`, then inherited by N9). Not done as a programme-wide
  exercise across turnover, capacity, ruin.
* **§14 N2's dependence treatment** — not done. `n_effective ≈ 24.8` is still a
  single equicorrelation shortcut and should still be treated as planning.
* **§6's ladder is incomplete** — no implied-vol rungs, and the residual-target
  regression (`future_rv − baseline`) against event/semantic features was not
  reached. Stage 1 only.
* **The paid night** — window opens 19:30 UTC tonight. **Not run.** Your call
  stands at ≤12:20 UTC tomorrow; the review's 10:30 UTC Monday is inside that.
* **The LIVE_FORWARD quarantine** — unblocked, still attended, still yours.

---

## 11. DOLLARS SPENT / INFORMATION GAINED

**$0.00.** Zero paid LLM calls. Every result above is arithmetic on data already
held, and N9 was designed specifically to answer for free the question that
decides how the LLM dollar should be spent. The answer — the grammar *can*
express rules that mark uncovered moves — is what licenses paying for autopsies
next, and it would have been discovered after the spend rather than before it.

---

## 12. SHAs

| | |
|---|---|
| `612566a` | four verdict labels corrected; the false kill compiled into `n4_precursor_coverage.py` |
| `7fe58b8` | **N4B** — the library refuted as a de-risking trigger |
| `192aaa0` | **N1** ran; the ledger volume question closed; §56 verified live |
| `3de2e6c` | **N9** — the grammar search, and the SS37 diagnostic that saved a false kill |
| `7dc9392` | **N9 confirmation** — lift 1.271 on securities declared before they were touched |
| `9aea3ed` | **N12** — vol-targeted sizing, and `constant_half` = `buy_hold` |
| `d7172fc` | **N11 / RISK-RESIDUAL-1 stage 1** — the ladder, and its premise refuted |
| `a0a26bf` | the tree guard, made actionable |
| `8b93610` | **R13** (Aegis module) |

CI green on `1086c65`; `a0a26bf` in progress at the time of writing and must be
confirmed before it is called shipped.

---

## 13. NEXT BINDING BOTTLENECK

**Candidate GENERATION at the episode level, and it is now the only thing in
the way.**

The referee is in good order — this session added an equivalence test, an
effect-size gate at registration and a placebo-controlled aggregate, and used
all three to *sharpen* results rather than to kill them. What it is refereeing
is six mechanisms and one grammar search.

N9 says the eight-feature grammar can express rules that mark uncovered moves,
at a lift too small to trade. The two ways forward from that are (a) more
episodes through the factory (§5), and (b) **a wider vocabulary** — because
every rule the atlas can currently express is a function of price and VIX, and
the 1.271 ceiling may be the vocabulary's ceiling rather than the market's.

**(b) is the cheaper diagnosis and I did not run it.** Re-running N9's search
with event, revision, flow and liquidity features admitted to the grammar would
say whether the ceiling moves. If it does, the factory has something to find. If
it does not, the factory will produce a thousand stories that compile into the
same 1.27.

---

## 14. THE SEVEN CLAIMS IN HERE MOST LIKELY TO BE WRONG

Kept, per order 3 §1.

1. **N4B's `se` comes from a block bootstrap that shares one draw across six
   co-moving ETFs.** That is the conservative choice, but it is one choice, and
   the whole `RULED_OUT` verdict rests on it.
2. **N9's confirmation holds out securities, not period.** The amendment
   declared "full history", so the confirmation slice overlaps the training
   *period*. A cleaner test holds out both; this one holds out one.
3. **N9's 60-day cells disagree between slices** (0.905 at p = 0.428 foreign,
   1.330 at p = 0.075 confirmation). I read that as a reason to trust neither.
   Someone could read it as the confirmation rescuing the horizon.
4. **N12's drawdown evidence is one path per security.** Block resampling
   destroys the path and max drawdown is a path statistic, so the honest
   drawdown number has no interval at all — I reported the full-sample matched
   paths and said so, but "3/4 with mean −6.87pp" is four correlated markets.
5. **N11's ladder has no implied-vol rung**, and I am claiming a *powered* null
   among the realised-vol rungs. If implied information belongs in the ladder,
   the null is about a ladder nobody would have built on purpose.
6. **The `L_min` formula assumes a single de-risking action with a fixed cost
   and no partial sizing.** A policy that scales exposure continuously has
   different economics, and the margin would move — possibly a lot.
7. **The ledger reconstruction rests on log lines from one deployment.** They
   are decisive for `7e2bbe35`, and I did not read logs from the deployments
   before it because they are past retention. If the mount ever differed, it
   differed earlier than any evidence I can now reach.

— builder, 2026-08-16
