# GRAND-ARENA-1 PHASE 1 — the known-answer worlds

**Run 2026-08-12. 12 worlds x 9 learners = 82 scored cells.**
Pre-registration: `Aegis module/TRIALS/PREREG_GRAND_ARENA_KNOWN_WORLDS_1.md`
(committed before the sweep, commit `05e5315`).
Runner: `Aegis module/scripts/run_known_world_1.py` ·
Artifact: `Aegis module/data/factory/known_world_1_results.json`.

---

## 0. Why this exists, and what it can license

Before any learner is believed when it reports an exit rule, a regime, or a
specialist's reliability in a real market, it must first prove it can
**rediscover a rule we planted by hand**. A learner that cannot recover a known
answer has not earned the right to be believed when it reports an unknown one.

This phase can fail. A failure here invalidates the interpretation of every
later phase — that is its purpose.

**It licenses exactly one class of sentence:** *learner X can (or cannot)
recover mechanism Y at this signal-to-noise on a panel of this size.* It
licenses **no** claim about real markets, no promotion, no lane, no money.
Synthetic performance is never alpha evidence, and this document does not
become one by being long.

---

## 1. THE NEGATIVE CONTROLS — read these first

Three cells matter more than every success in this document, because they are
the exact failure mode that would make every real-market result untrustworthy.

### 1.1 WORLD-I — pure correlated noise. **13 of 13 correct.**

Nothing predicts anything forward. `f_mom` was deliberately given a
**contemporaneous** correlation of ρ ≈ 0.43 with the same month's idiosyncratic
return and **zero** forward relationship: the classic apparent signal, and a
leakage tripwire.

| Learner | out-of-sample IC | MDE | ratio | verdict |
|---|---|---|---|---|
| ridge | −0.0052 | 0.0116 | 0.45x | **CORRECT-NULL** |
| logistic | −0.0010 | 0.0114 | 0.09x | **CORRECT-NULL** |
| random forest | −0.0049 | 0.0113 | 0.43x | **CORRECT-NULL** |
| LightGBM | −0.0027 | 0.0107 | 0.25x | **CORRECT-NULL** |
| MLP (torch) | −0.0097 | 0.0113 | 0.86x | **CORRECT-NULL** |
| evolutionary | −0.0019 | 0.0102 | 0.19x | **CORRECT-NULL** |
| HMM regime | −0.0050 | 0.0108 | 0.47x | **CORRECT-NULL** |
| contextual bandit | +0.0009/yr | 0.0140 | 0.07x | **CORRECT-NULL** |

**And the tripwire has teeth — this is the part that makes the row above mean
something.** A CORRECT-NULL is worthless if the world could not have produced a
false positive in the first place, so the defect the world was built to catch
was run deliberately: align the score with the **same** month's return instead
of the next one — the ordinary off-by-one — and the identical harness prints

> **IC = +0.4283, t = 87.8, MDE 0.0098 — forty-four times its own MDE.**

That is what a one-month misalignment would have looked like. No learner came
within a tenth of its MDE of it. The null verdicts are informative, not vacuous.

The contextual bandit's behaviour is the cleanest single exhibit: offered four
tilts, it allocated **100% to `no_tilt` in every sector**.

### 1.2 WORLD-L — dynamic exposure adds nothing. **5 of 5 correct, but one was close, and the reason it stayed correct was NOT the learner.**

Market returns are i.i.d. with constant volatility; every market observable is
noise. 499 test months.

| Learner | timing gain at **matched** average exposure | MDE | ratio | verdict |
|---|---|---|---|---|
| ridge | +0.0090/yr | 0.0095 | 0.95x | **CORRECT-NULL** |
| logistic | +0.0037/yr | 0.0080 | 0.46x | **CORRECT-NULL** |
| LightGBM | +0.0108/yr | 0.0145 | 0.74x | **CORRECT-NULL** |
| offline-Q (conservative) | +0.0088/yr | 0.0185 | 0.47x | **CORRECT-NULL** |
| evolutionary | +0.0189/yr | 0.0243 | 0.78x | **CORRECT-NULL** |

**The evolutionary policy did invent a timing rule.** It sat at zero exposure in
**52%** of months and at full exposure in 26%, and its raw annualised Sharpe was
**0.500 against the static 0.478**. Reported the way a dashboard would report it
— "the timing overlay improved Sharpe" — that is a discovery. It survives
neither of the two disciplines applied here:

1. **matched average exposure.** A policy that holds more of a positive equity
   premium earns more without timing anything. Comparing against a static book
   at the *same* mean exposure removes that channel, and the gain falls to
   +1.89%/yr;
2. **its own MDE.** A policy that swings between 0 and 1 has a violent
   difference series, so its 80%-power MDE is 2.43%/yr. +1.89 is inside it.

The conservative offline-Q did the same thing more quietly (12% zero exposure,
50% full, +0.88%/yr inside an MDE of 1.85%).

**The finding is therefore not "the learners refused to invent a timing edge."
It is "two of five learners invented one, and the statistical discipline caught
it."** In this programme's own history — three nights pointing at sizing rather
than timing — that is the more useful sentence.

### 1.3 WORLD-J — a real gross edge that costs kill. **7 of 7 refused to trade it.**

Gross edge +12%/yr on a fast (AR 0.15) signal at 65 bps one-way per leg, with
near-complete monthly turnover.

| Learner | gross IC (MDE) | net spread /yr (MDE) | **breakeven one-way cost** | verdict |
|---|---|---|---|---|
| ridge | +0.0268 (0.0107) | −0.2276 (0.0377) | 17.5 bps | **RECOVERED** |
| logistic | +0.0288 (0.0101) | −0.2126 (0.0366) | 20.6 bps | **RECOVERED** |
| random forest | +0.0233 (0.0103) | −0.2515 (0.0363) | 12.5 bps | **RECOVERED** |
| LightGBM | +0.0173 (0.0099) | −0.2509 (0.0351) | 12.6 bps | **RECOVERED** |
| MLP (torch) | +0.0021 (0.0100) | −0.2882 (0.0386) | 4.8 bps | MISSED (no gross edge found) |
| evolutionary | +0.0243 (0.0102) | −0.2274 (0.0343) | 17.5 bps | **RECOVERED** |
| HMM regime | +0.0263 (0.0107) | −0.2292 (0.0377) | 17.1 bps | **RECOVERED** |

Not one cell declared a net edge. **Stated honestly, this is the weakest of the
three negative controls**: at 65 bps against an oracle breakeven of 25.4 bps,
the cost exceeds the gross edge by 2.5x, so refusing it demonstrates
cost-awareness only coarsely. The breakeven column is the graded version and is
the number to carry forward: the *best* learner here needed costs below 21 bps,
the world charged 65, and the oracle itself needed below 25. A Phase 2 variant
with costs set near the breakeven is the harder test and has not been run.

### 1.4 Negative controls, in one line

**0 false positives in 82 cells; 13 of 13 null-world cells correct; the leakage
tripwire fires at 44x MDE when deliberately tripped.** Every learner tested is
clean on the negative controls.

---

## 2. The recovery matrix

| World | ridge | logit | RF | LGBM | MLP | evo | HMM | bandit | fitQ |
|---|---|---|---|---|---|---|---|---|---|
| **A** momentum pays | **REC** | **REC** | **REC** | **REC** | MISS | **REC** | **REC** | **REC** | — |
| **B** momentum reverts | **REC** | **REC** | **REC** | **REC** | **REC** | **REC** | **REC** | MISS* | — |
| **C** latent regimes | PART | PART | PART | MISS | PART | PART | PART | — | — |
| **D** noisy precursor | **REC** | **REC** | — | MISS | — | MISS | — | — | **REC** |
| **E** revision gate | PART | PART | MISS | MISS | MISS | MISS | MISS | — | — |
| **F** valuation threshold | PART | PART | MISS | **REC** | MISS | PART | PART | — | — |
| **G** specialist A / biotech | MISS | MISS | MISS | **REC** | MISS | MISS | MISS | **REC** | — |
| **H** specialist B / semis | PART | PART | MISS | MISS | MISS | PART | PART | **REC** | — |
| **I** *pure noise* | **NULL** | **NULL** | **NULL** | **NULL** | **NULL** | **NULL** | **NULL** | **NULL** | — |
| **J** cost-killed edge | **REC** | **REC** | **REC** | **REC** | MISS | **REC** | **REC** | — | — |
| **K** replace, not cash | MISS | — | — | MISS | — | MISS | — | — | MISS |
| **L** *no timing edge* | **NULL** | **NULL** | — | **NULL** | — | **NULL** | — | — | **NULL** |

REC = RECOVERED · PART = PARTIAL (detected, mechanism not recovered) ·
MISS = MISSED (below its own MDE) · NULL = CORRECT-NULL. Dashes are
not-applicable, not failures.

**Totals: 27 RECOVERED · 16 PARTIAL · 26 MISSED · 13 CORRECT-NULL · 0
FALSE-POSITIVE.**

\* World B's bandit is a labelling artefact I am not going to quietly fix after
the fact: it allocated **0.0%** to the anti-predictive momentum arm — exactly
the right behaviour, and the mechanism probe passed — but its gain over the
uniform-arm control (+1.02%/yr) sat inside its MDE (1.91%/yr). The
pre-registered rule ranks the primary metric first, so it reads MISSED. The
honest statement is *"did the right thing, undetectably."*

---

## 3. Ceilings — was the world recoverable at all?

Every MISSED has two readings: the learner failed, or nobody could have
succeeded. Only this table tells them apart. The oracle uses truth no learner
sees (the latent state, the gate, the skilled sector).

| World | oracle primary | MDE | ratio | best learner achieved |
|---|---|---|---|---|
| A | IC +0.0291 | 0.0097 | 3.00x | 0.0217 (ridge), 75% of ceiling |
| B | IC +0.0386 | 0.0098 | 3.94x | 0.0338 (logit), 88% |
| C | IC +0.0392 | 0.0101 | 3.90x | 0.0240 (ridge), 61% |
| D | +3.01%/yr | 0.0152 | 1.98x | +3.37%/yr (offline-Q) |
| E | IC +0.0206 | 0.0099 | 2.08x | 0.0105 (logit), 51% |
| F | IC +0.0439 | 0.0104 | 4.23x | 0.0226 (LGBM), 51% |
| G | IC +0.0402 | 0.0113 | 3.55x | 0.0138 (LGBM), 34% |
| H | IC +0.0253 | 0.0105 | 2.40x | 0.0156 (evo), 62% |
| J | IC +0.0386 gross | 0.0108 | 3.58x | 0.0288 (logit), 75% |
| K | rule +3.61%/yr | 0.0122 | 2.97x | **none above its MDE** |

**Every signal world was recoverable.** The smallest ceilings — world D at 1.98x
its MDE and world E at 2.08x — still cleared the bar an ordinary result has to
clear. So the 26 MISSED cells are learner failures, not design failures, with
the single exception of world K, where the learners' own behaviour inflated
their MDEs past the ceiling (§4).

Two ceilings worth naming separately:

* **World C regime.** A Bayes filter with the TRUE transition matrix and TRUE
  emission parameters reaches **76.0%** state accuracy on monthly returns
  (chance 50%). The fitted 2-state Gaussian HMM reached **58.8%** — above its
  own MDE of 7.1pp, so the regime *was* detected, but nowhere near the ceiling,
  and a regime-conditional model built on a 59%-accurate state is a model
  conditioned mostly on noise. That is why every world-C cell is PARTIAL:
  every learner beat its MDE on prediction, **none** recovered the mechanism.
* **World D peak-calling.** Perfect foresight over the bad months is worth
  +19.03%/yr; the population-form *probabilistic* policy on the observable
  precursor is worth +3.01%/yr. **84% of the available value is unreachable in
  principle** — which is the world's whole point, and the answer to
  "sell before the war" in known-answer form.

---

## 4. What the failures say

**MLP (torch) — 1 recovery in 9 cells, and it missed the linear world A.** The
prior held: a neural net that loses to ridge on a linearly-planted world is
telling you about capacity-vs-sample-size, not about the world. With ~50k
training rows at IC 0.03, the net's variance swamps the signal. It never
produced a false positive, so it is not dangerous — it is just not useful at
this sample size.

**LightGBM is the only learner that recovered a threshold (F) and a
sector-conditional specialist (G) from the cross-section**, and it is the only
learner with 5 recoveries. It also has 5 MISSES, including world H — the mirror
image of world G it recovered. Reading those two together: LightGBM's
conditional recovery is real but **not reliable**; on a smaller planted effect
(H's ceiling is 2.40x vs G's 3.55x) it fell to 0.60x its MDE. One recovered
conditional mechanism is not a general capability.

**Ridge and logistic are the most consistent detectors and the weakest
explainers**: 4 recoveries and 4 PARTIALs each. A PARTIAL here means *it made
money-shaped predictions without recovering the structure* — in world F it
tilted toward momentum on average while the world reverses momentum for
expensive names. That is the specific way a linear model is dangerous: right on
average, wrong exactly where the money is lost.

**The contextual bandit was the strongest specialist-attribution instrument by a
wide margin.** It recovered G and H where 6 of 7 cross-sectional learners
failed, allocating **100%** of its pulls to the skilled specialist inside the
skilled sector, and **0.0% / 0.5%** to the decoy specialist anywhere. Its own
caveat: in world G it still gave the true specialist 27% of its pulls in sectors
where that specialist has no skill.

**The bandit only worked after a scaling fix, and the pre-fix version is the
more instructive artefact.** Textbook LinUCB assumes rewards in [0, 1]; these
rewards are monthly spreads of order 0.02, so the exploration bonus exceeded
every arm-value difference by ~20x. The bandit ran green, reported no errors,
allocated 35% to the skilled arm instead of 100%, and returned a gain below its
MDE. **It was a uniform random policy wearing a bandit's clothes** — this
programme's house failure mode (code that runs and silently does nothing),
caught only because a known-answer world said what the number should have been.

**World K is the sharpest single result in the document.** All four action
learners MISSED, and the reason is not that they failed to find the replacement
rule — ridge found it (replace chosen 33pp more often on stale names) and so did
the evolutionary search (29pp). They missed because **every learner reached for
cash**, at 20% / 28% / 32% / **39%** of all actions, in a world where cash is
never the optimal action. Cash is a market-level bet, so cash actions injected
market volatility into the policy's value series and pushed each learner's MDE
to 4.1–5.1%/yr against a rule ceiling of 3.6%/yr. **They made themselves
undetectable by de-risking.**

Worse, the *conservative* offline-Q was the worst offender at 39% cash. That is
structural, not incidental: a pessimism penalty subtracts an uncertainty
allowance from every action's value, and **cash has no uncertainty to be
pessimistic about** — its payoff is exactly zero, always. A conservative
action-value learner is therefore systematically biased toward the do-nothing
action. NIGHT-12 measured that `sell_to_cash` was never best in 60 rows of the
real book; this world says an offline-RL exit learner would have reached for it
anyway, and would have called the resulting variance "risk management."

---

## 5. Which learners are trustworthy for Phase 6

| Learner | negative controls | recoveries | verdict for Phase 6 |
|---|---|---|---|
| **contextual bandit** | clean (I) | A, G, H | **TRUSTED for specialist/sector attribution.** The only instrument that recovered conditional specialist skill. Reward scale must be asserted in a test, not assumed. |
| **ridge / logistic** | clean (I, L) | A, B, D, J | **TRUSTED as detectors, NOT as explainers.** Use for "is there anything here"; never read a PARTIAL as a mechanism. |
| **LightGBM** | clean (I, L) | A, B, F, G, J | **TRUSTED with a stated caveat.** The only cross-sectional conditional recovery — and it failed the mirror world. Any conditional structure it reports needs a second, independent confirmation. |
| **HMM regime** | clean (I) | A, B, J | **NOT TRUSTED as a regime instrument.** 58.8% state accuracy against a 76.0% ceiling; it never recovered the regime mechanism it exists to recover. Its recoveries are its embedded ridge, not its HMM. |
| **evolutionary search** | clean (I, L) — but see §1.2 | A, B, J | **CONDITIONALLY TRUSTED, discipline-dependent.** It invented a timing rule in world L that only matched-exposure comparison plus an MDE refused. Never report an evolutionary result without both. |
| **random forest** | clean (I) | A, B, J | Usable, dominated by LightGBM everywhere. |
| **offline-Q (conservative)** | clean (I, L) | D | **NOT TRUSTED for exit/action work.** Structurally biased toward cash (§4). Any use in EXIT-RL must carry an explicit no-op penalty or a cash budget, and must be re-tested on world K. |
| **MLP (torch)** | clean (I) | B | **NOT TRUSTED at this sample size.** 1 of 9, missed the linear world. Not dangerous, just not useful. |

---

## 6. §20 batch self-check

* 82 cells, 13 in null worlds. **0 false positives** against a nominal
  expectation of 0.59 at a 4.55% two-sided rate.
* **Median effective distinct learners per world: 2.36** (7 nominal learners,
  mean absolute pairwise correlation of out-of-sample scores 0.21–0.41). Seven
  learners are not seven independent chances to find something; they are about
  two and a third. The honest expected false-positive count is therefore lower
  than the nominal 0.59, which makes the observed zero *less* impressive than
  it looks — and makes any single future false positive worth more than it
  looks.

---

## 7. What this does NOT license, and what is still owed

1. **No real-market claim of any kind.** Nothing here is evidence that any
   strategy makes money. No trial in the registry is advanced by this document.
2. **Sample-size specificity.** Every verdict is conditional on 200 names x 300
   months (600 for the two market-level worlds), 8 purged and embargoed
   walk-forward folds, and planted ICs in the 0.02–0.04 band. A learner that
   missed here may recover on a longer panel; a learner that recovered here may
   not survive a shorter one.
3. **World J is the easy version of its own question** (§1.3). The near-breakeven
   variant has not been run.
4. **World K's logging policy is uniform-random and its book is resampled each
   month**, so it is a one-step contextual action problem with no sequential
   structure. Real logged books are nothing like this, and a learner that only
   works under uniform logging has not been shown to work.
5. **World C's regime result is about a 2-state Gaussian HMM on two market
   observables.** It does not close the question of whether some other regime
   instrument reaches the 76% Bayes ceiling.
6. **The three calibration disclosures in the pre-registration stand** (§7 of
   `PREREG_GRAND_ARENA_KNOWN_WORLDS_1.md`): worlds D, K and L were re-specified
   before the sweep because their own optimal policies sat below their MDEs, and
   every such decision came from an oracle calculation, never from a learner's
   result. Worlds E, F, G and H were **not** power-checked in advance — their
   ceilings were computed afterwards and all cleared 2x, but that was luck, and
   Phase 2 should compute ceilings before the sweep rather than after it.

**The headline, in one sentence:** every learner tested is clean on the negative
controls, the leakage tripwire fires at 44x MDE when deliberately tripped, and
the two learners that came closest to inventing an edge from noise — the
evolutionary search and the conservative offline-Q — were stopped by
matched-exposure comparison and CANON §19, not by their own good judgement.
