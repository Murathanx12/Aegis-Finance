# REVIEW 2026-09-29 — the shadow book `439fd84f869744e0` and nn_lab's ensemble trust weights (adversarial)

Reviewer stance: a sceptical investor. Scope: `scripts/shadow_bayes_rule.py`, the frozen book
`439fd84f869744e0` and its three twins in `backend/data/optimus/llm_portfolio/books.jsonl`
(lines 309-312), `backend/data/optimus/shadow_bayes/` (the registration and two rule receipts), the
twin builder `backend/services/llm_portfolio.py:526-605`, and the trust and ensemble path in
`nn_lab/loop.py:325-456` and `nn_lab/nightly.py:281-331`, read against
`backend/data/optimus/nn_lab/receipts/nightly_20260929T003003Z.json` and
`wf_20260929_post_review.json`. `docs/reviews/REVIEW_2026-09-29_NN_LAB.md` (F1-F10) was read first
and is not repeated here. No file was changed except this one. Every number is from a receipt on
disk, or was computed in this review and says so.

## RESULTS SCOREBOARD

| item | value |
|---|---|
| RESULT IMPROVEMENT | **NONE**. Nothing here has a graded outcome. The book enters at the 2026-09-29 open. nn_lab has `graded_total: 0` |
| Money at risk | **$0**. No broker path in either build (verified below) |
| Shadow book | 4 names: JAZZ 32.8%, TS 31.1%, SNDR 19.2%, TSM 16.9%. The "live-size" rule is 3.7% sleeve + 96.3% SPY |
| Stated edge | P(beats SPY over 21 sessions) from 0.506 to 0.510. Posterior momentum edge +0.22%/month |
| Ensemble weights (h21) | lgbm 0.391 / ridge 0.313 / mom_12_1 0.277 / nn 0.019. **All from the walk-forward backtest; zero forward grades** |
| Independent selectors added | 0. The shadow book is 12-1 momentum among the funnel's 45 names |
| LLM spend | $0 |
| Score | **48 / 100**: the priors are honestly centred on zero, but the weights are backtest IC ratios the shrinkage cannot touch, and the book's registered test is a coin flip against a twin matched on the wrong things |

## Answers to the four questions, short

1. **Is the prior centred on zero?** Yes, in both builds. Shadow: `N(0, TAU²)` with TAU 0.005, and a
   component with no measurement gets exactly 0 (`shadow_bayes_rule.py:114-117`, `:125-129`). nn_lab:
   `N(0, 0.03²)`, and the posterior mean is `(n_f·m_f + n_w·m_w)/(n + k)` (`loop.py:340-347`). **But
   the ensemble then divides by the total** (`loop.py:445-456`), so the shrinkage cancels in the
   weights. See F1.
2. **Can the weights move on ungraded or in-sample data?** Yes. With `graded_total: 0`, every trust
   value has `source: walk_forward_only`. The weights change whenever a newer `wf_*.json` with
   `post_review: true` appears (`nightly.py:281-304`), and no forward grade is needed for that.
3. **Is the twin matched?** Only on the liquidity band (4 bands by median dollar volume,
   `xs_ranker.py:426-435`, `llm_portfolio.py:585-603`). There is no sector, volatility, beta or
   momentum match, and the seed is not recorded. The evidence the rule is built on used a much
   stricter twin. See F2.
4. **Can it reach a broker?** No. `shadow_bayes_rule.py:45-62` imports only stdlib, numpy, pandas
   and `backend.config`. `llm_portfolio.py` contains no `broker`, `alpaca`, `submit` or `pc_broker`
   string. The nn_lab receipt says `broker_authority: "NONE: writes predictions, never orders"`.

## Findings, most severe first

### F1: HIGH. The ensemble weights are the backtest's IC ratios, and the "shrink toward zero" cancels out

**Claim** (commit message and `loop.py:18-27`): each model's trust is a posterior shrunk toward zero,
and the ensemble is weighted by that trust.

**Evidence.**
* `nightly_20260929T003003Z.json`: `grade.graded_now 0`, `graded_total 0`. Every roster model at
  every horizon has `source: walk_forward_only` and `n_forward_blocks: 0`.
* At h21 the trust values are lgbm 0.007451, ridge 0.005969, mom 0.005274 and nn 0.000352. Each one
  is 0.4186 × the walk-forward mean IC (0.0178 / 0.01426 / 0.0126 / 0.00084 in
  `wf_20260929_post_review.json`).
* `ensemble_scores` normalises by `tot` (`loop.py:445-456`). The common factor 0.4186 therefore
  cancels: 0.0178 / (0.0178+0.01426+0.0126+0.00084) = **0.391**, which is exactly the frozen weight.
  **The prior has no effect on the ensemble's composition.** It only matters if every trust value
  is ≤ 0.
* The walk-forward input is not clean out-of-sample data. The post-review rerun changed features
  and the variant AFTER the same 2019-2026 test blocks had been read, and NN_LAB F10 notes the
  variant was chosen on test data. So the weights are ratios of backtest statistics from a window
  that has been looked at more than once.
* **The weights move without forward data.** `wf_record()` takes the newest `wf_*.json` by filename
  with `post_review: true` (`nightly.py:283-289`). Any rerun, for example after the nightly table
  rewrite that NN_LAB F5 describes, changes every weight. There is no receipt hash pin.
* **The walk-forward's effective weight is double-counted.** `trust_table` passes `n_blocks` (80 at
  h21, overlapping) and not `n_blocks_strict` (40) (`loop.py:367-368`), so the walk-forward counts
  as 8.0 effective blocks and not 4.0. That halves the prior's pull on the trust magnitudes
  (computed here from the receipt).

**Consequence.** Nothing trades on the ensemble today. `contest_desk` displays nn_lab columns only.
But a "v1" shadow book that uses "its trust-weighted ensemble for direction", as
`night_report_2026-09-29.md` §5 proposes, would size on backtest IC ratios presented as learned
trust. The trust magnitude would also scale nothing, because it is normalised away.

**Fix.** (a) Until at least one forward block exists, the ensemble should be the zero, or an equal
weight that is labelled as such. (b) Keep the trust as a SCALE: `score = Σ trust_m · rank_m`, with
no division by `Σ trust`, so that shrinkage shrinks the bet. (c) Pin the walk-forward receipt by
sha256 in `nn_lab/config.py`, and refuse a silent swap. (d) Use `n_blocks_strict`.
**Who decides:** the builder for (b)-(d). The owner decides whether a backtest may seed direction
trust at all.

### F2: HIGH. The twin is matched on liquidity only, and the evidence was measured against a much stricter twin

**Evidence.**
* The shadow book's primary comparison is "book minus `random_same_band` twin `ec29c635db8ac686`"
  (registration, `primary_comparison`). That twin replaces each name with a random live name from
  the same one of four dollar-volume bands (`llm_portfolio.py:585-603`). The draws were
  JAZZ→CM (a Canadian bank), TS→VNT, SNDR→LMAT and TSM→ALAB (`books.jsonl:312`). Sector, beta and
  volatility are not matched, and neither is **momentum**.
* The momentum edge the rule uses (`EVIDENCE["momentum_12_1"]`, `shadow_bayes_rule.py:86-90`) comes
  from `matched_twins_2026-09-27T082553Z.json`. Its `matching` is "size band × vol_63 tercile ×
  **mom_252_21 tercile**". That edge is momentum selection **within** the top momentum tercile, net
  of volatility.
* The forward test therefore measures the whole momentum factor plus a volatility mismatch against
  a random name. The posterior it claims to calibrate had both of those removed.
* The twin's seed is in neither `books.jsonl:312` nor the registration. The draw cannot be
  reproduced, and a second draw cannot be shown to be the first.

**Consequence.** If the sleeve beats its twin, that could be factor momentum, which was already
known and already priced in the "IS BETA" discussion of 09-27, or luck. It would not confirm the
+0.22%/month posterior. If the sleeve trails, that could be a single volatile replacement: ALAB
against TSM.

**Fix.** Mint the shadow's twin with the same matching as its evidence (band × vol tercile × mom
tercile), average 21 draws the way `twin21` does, and record the seed in the book row. **Who:**
builder. Because the book has already entered, this is a sidecar twin frozen now, never an edit to
the frozen one.

### F3: HIGH. The registered kill rule and the Brier falsifier are coin flips

**Evidence** (computed in this review from the book's weights and the rule receipt's
`sigma_resid_21` of 7.5-9.0% per name):
* Effective number of names = 1/Σw² = 1/(0.108+0.096+0.037+0.028) ≈ **3.7**.
* 63-session idiosyncratic sd per name is about 8% × √3 ≈ 14%. For the sleeve it is about
  14%/√3.7 ≈ 7%, and the sleeve-minus-twin sd is about 10%.
* The expected edge at the posterior is about 0.17%/month × 3 ≈ 0.5%.
  P(sleeve < twin | the posterior is TRUE) ≈ Φ(−0.5/10) ≈ **0.48**.
* The kill rule ("sleeve trails its random twin at 63 sessions → FAILED_VARIANT") therefore kills a
  correct rule 48% of the time and a worthless one 50% of the time.
* The Brier falsifier ("Brier worse than 0.25", `shadow_bayes_rule.py:282-283`): with p between
  0.506 and 0.510, each name scores about 0.240 if it beats SPY and about 0.260 if it does not. The
  falsifier fires whenever fewer than half of four outcomes beat SPY, which is a coin flip. The
  registration admits the low resolution. It does not admit that the falsifier is a coin.

**Consequence.** On 2026-12-24 the programme will write FAILED_VARIANT or "not failed" on about
2 percentage points of information. The label "FAILED_VARIANT" then attaches to a rule that was
never tested.

**Fix.** Grade the RULE, not four names. Every night, record P(beat SPY) and alpha for all 38
scored candidates, then grade the calibration and the rank IC of alpha over all of them, pooled
across nightly vintages. That needs no new book and no broker, just an append-only file. Replace
the kill rule with a pre-stated MDE and the verdict CANNOT_DISTINGUISH when the result is under
it. **Who:** the builder for the file; the owner for replacing a registered kill rule. Because
the book is registered, the change must be a dated amendment written before the first read.

### F4: MEDIUM-HIGH. The frozen book is a threshold artefact, and the ROI table presents it as a $1M account

**Evidence.**
* `MIN_WEIGHT = 0.005` is applied AFTER the sleeve scale of 0.144 (`shadow_bayes_rule.py:225-228`).
* In the rule receipt, GOOGL's live weight is 0.0048 and is dropped. INCY 0.0046, KEX 0.0043, STNG,
  PDS and CSTM at about 0.004, and CHD and WDS at about 0.003 are dropped too. `MAX_NAMES = 10`
  never binds.
* The survivors are then renormalised to 100% of the sleeve (`:265-279`). The result is a 4-name
  book with 32.8% in JAZZ, which is not what the rule would hold. The rule's output is 3.7% of
  capital spread over the same names.
* `paper_accounts/roi_2026-09-28T235128Z.nobroker.json` lists "SHADOW_BAYES_v0 sleeve" as an
  account with `start_capital 1000000`.

**Consequence.** The ROI surface will show a 4-name concentrated book's swings as the result of
"the rule that acts on probabilities". That book is 27× more concentrated than the rule's own
sizing, and a 5 bp change in a threshold decided its membership.

**Fix.** Apply `MIN_WEIGHT` to `w_raw`, or freeze the sleeve at its top `MAX_NAMES` raw weights. On
the ROI row, print the live-size NAV (0.037 × sleeve + 0.963 × SPY) beside the sleeve. **Who:**
builder.

### F5: MEDIUM. The evidence chosen was the favourable twin draw; one input is declared, not measured; the "sealed" window is not sealed

**Evidence** (`matched_twins_2026-09-27T082553Z.json`, cell `mom_12_1@k20`):
* The rule uses draw 0: dev +2.17%/month (t 2.59) and sealed +0.79% (t 0.46). The same receipt
  calls `twin21` "the lower-noise twin the family pool reads": dev +1.81% (t 2.28) and sealed
  **+0.36% (t 0.24)**.
* In the sealed window, the 20 extra draws give a mean rule-minus-twin CAGR of **−2.26%**
  (sd 12.8%), against +4.04% for draw 0.
* Recomputed here with `twin21`, the momentum posterior is about **+0.18%/month**, not +0.22%.
* The 2024-26 window "taken at face value" (`:22-24`) has been read repeatedly since 09-26 (the
  library, freeze_gate and 09-27 reviews), so treating it as sealed is not honest either.
* `ranker_lgbm` is `(-0.0007, -0.7, 122, "sealed")`, where the t of −0.7 is "declared"
  (`shadow_bayes_rule.py:98-100`). That gives an SE of 0.10%/month, the tightest in the set, with a
  shrink of 0.96. The strongest-held belief in the rule rests on an invented t. It penalises 25 of
  the 45 candidates (those in the ranker's top decile) by −0.067%.

**Consequence.** The edge is overstated by about 20%, and the exclusion of ranker names rests on a
number that was never computed. Neither changes the sign. Both are the "headline number without a
receipt" pattern.

**Fix.** Use `twin21` with its t and inflate the "sealed" SE as well. Compute the ranker's net t
from the bake-off series or give it no observation. **Who:** builder, as a v1 note. v0 is frozen
and stays as it is.

### F6: MEDIUM. "P(beats SPY)" is not a probability of beating SPY, and the secondary read measures cash vs SPY

**Evidence.**
* `alpha_i` is built from edges measured against a **matched twin** (`:20-21`), not against SPY. The
  band-matched random portfolio has its own excess over SPY (the 09-27 lesson: the panel's random
  portfolio tilts to IWM).
* `s_i` uses residual volatility only (`:156-161`, `:215`) and leaves out the `(β−1)·SPY` variance
  of the excess return.
* Three of the four book names (JAZZ, SNDR, TSM) are already PROBE names in PC-PAPER
  (`current_plan_targets` in the rule receipt). The secondary comparison "live-size book vs
  PC-PAPER NAV" is therefore mostly 96% SPY against about 80% cash: a market-beta read.

**Consequence.** Whatever the Brier score is, it will partly grade the market over those 21
sessions. Whatever the secondary read says, it will grade the equity premium.

**Fix.** State the probability against the twin, or add the market term to `s_i`. Report the
secondary read beta-adjusted, or against 0.2 × SPY. **Who:** builder. Whether idle capital sits in
SPY or cash is the owner's call, already on the list in night_report §6.2.

### F7: MEDIUM. Nothing that makes this a freeze is in git

**Evidence.**
* `git show HEAD:backend/data/optimus/llm_portfolio/books.jsonl | grep -c 439fd84f869744e0` returns
  **0**. The book row exists only in the modified working tree.
* `backend/data/optimus/shadow_bayes/` (the registration, both rule receipts and the book JSON) is
  untracked (`??`).
* The registration says the rule code was "uncommitted at registration". It landed in `c0ac5310`
  at 00:32 UTC on 09-29, before the 13:30 UTC entry, which is fine.
* `nn_lab/config.py:86-90` labels `frozen_ledger.jsonl`, `forward_grades.jsonl` and `trust.jsonl`
  **TRACKED**, and all three are untracked (`??`).

**Consequence.** The repo has already lost ~1,200 ledger rows to a `reset --hard`
(memory 09-24). Until these are committed, the freeze time and the twin draw cannot be proved, and
a tidy-up can erase them.

**Fix.** Commit `books.jsonl`, `shadow_bayes/` and the three nn_lab ledgers in the next commit, and
add the ledgers to the tracked set that `config.py` already claims. **Who:** builder, now.

### F8: LOW. The in-charge switch can fire on a night with no roster grade

**Evidence.** `forward_added = graded_now > 0` (`nightly.py:608`). `graded_now` counts every new
grade row (`loop.py:319`), including the legacy v0 file, which is "never trusted"
(`nightly.py:246-248`), and the magnitude models. The first in-charge model (lgbm) was chosen on
walk-forward trust alone ("first night").

**Consequence.** Around 10-05, a night that grades only the legacy file, together with a
walk-forward rerun, can change the model in charge with no forward evidence for it.

**Fix.** Count only `DIRECTION_ROSTER` direction grades. **Who:** builder.

### F9: LOW, LATENT. The shadow rule reads the uncut bar file

**Evidence.** `BARS = prices_deep/bars.parquet` is read directly (`shadow_bayes_rule.py:65`,
`:140-145`), without `stitched_tickers.cut_reader_bars`. JAN and MLPI are among the 45 candidates,
and both are in `cut_and_resumed_inside_12_1_window` (`stitched_20260928T153245Z.json`). Tonight both
were refused for lack of a 63-session residual volatility, so no harm was done.

**Fix.** Call `cut_reader_bars` after loading. **Who:** builder.

**Adjacent, outside this build:** `contest_desk.nn_lab_prob` (`scripts/contest_desk.py:285-303`) reads
`nn_lab/predictions/pred_*.parquet`. The only file there is the pre-review legacy v0 file, the one
with the split leak (NN_LAB F1). The new loop writes to `frozen/`, so that column will read the
leaky file indefinitely. It is display-only and labelled EXPERIMENTAL.

**Process note.** The book was frozen against the TIER 1 roadmap's "no new book until 2026-10-26".
The registration says so and names who instructed it. That is an owner decision, and it is recorded
honestly.

## WHAT WORKS

* Both priors are genuinely centred on zero. An unmeasured component gets exactly zero, and the
  code says so on the receipt.
* The shadow rule's dev-window SE inflation, fractional Kelly and sleeve cap by tracking error are
  the right shape. The rule concluded "3.7% active, the rest SPY", which is the honest size of this
  evidence.
* The rule was frozen before entry, with three twins, a registration, a stated read date and a
  stated weakness. Nothing reaches a broker.
* nn_lab's in-charge model cannot change without a forward grade, apart from F8, and the receipt
  prints `source` per model. That is how F1 could be found in five minutes.

## WHAT DOES NOT

* Walk-forward IC ratios are presented as "trust". The shrinkage is normalised away, and the
  weights move whenever a backtest is rerun.
* The registered test cannot tell a right rule from a wrong one (48% vs 50%), against a twin that
  is not matched on the factor the rule bets on.
* The graded object is a 4-name threshold artefact and not the rule's output.
* The freeze is not in git.

## HIGHEST-EV EXPERIMENT

**Grade the rule's full candidate list every night, not the four-name book.** The rule already
computes alpha and P for about 38 names a night. Append those rows, with the rule hash, to one
tracked JSONL, and grade them at 21 sessions against twins matched like the evidence (band × vol ×
mom tercile, 21 draws). Report the rank IC of alpha, calibration by decile of P, and the
sleeve-minus-twin21 return per nightly vintage, pooled.

Cost: one script, $0, no new book, and no roadmap conflict. By 2026-12-24 that is about 60 vintages
× 38 names, against 4 names once. That turns a coin flip into a measurement with an MDE worth
stating. It is also the first forward evidence that could legitimately seed nn_lab trust for
`mom_12_1`, which sits in both builds.
