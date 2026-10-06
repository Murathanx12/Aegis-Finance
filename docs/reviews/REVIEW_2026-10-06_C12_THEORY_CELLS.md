# REVIEW — CHUNK C12: theory cells + family generation shrink (2026-10-06)

Adversarial review (Opus 5.5), read-only. Reviewed against WIP `f4dbd0c0` plus the working tree. I did not
re-run any cell. My recomputations read the saved events parquets and the CRSP daily files, and all
scratch output stayed outside the repo. This file is the only one I wrote.

## VERDICT

**The three FAILED_VARIANT labels stand. Two of the numbers behind them are wrong in size, and one
robustness sentence in the note is false.**

- (b) insider_hold: the daily-rebalanced band bias is **1.49 pp per 63 sessions, not 0.8**. Against a
  buy-and-hold band, the primary goes from −1.82% (t −5.75) to **−0.53% (t −1.68)**, so about 70% of
  the headline was benchmark.
- Against the market, the declared rule returns **CANNOT_DISTINGUISH, not FAILED_VARIANT**.
- (c) beat_streak's primary is not band-neutral as declared. Its validate sign flips between the band
  and the market benchmark.
- The streak cell tested post-announcement drift. Row 13 of the owner's table asks about the **next**
  announcement. On that question the data says something: streaks predict the next beat
  (61% → 81%), and the next reaction is larger after a long streak, not smaller.
- The generation shrink is a preference only for the EV multiplier. Its posterior ignores power, so it
  can starve families that are merely hard to measure. A family can also escape it by renaming itself.

**Score: 58 / 100.**

---

## Findings

### F1 — HIGH — The (b) band bias is about twice the stated size, and "FAILED_VARIANT either way" is false

The band index is the daily mean of CRSP `ret` over band members (`_measure`, `BD` → `BC`). That is a
daily-rebalanced equal-weight index, and it carries bid-ask bounce and rebalancing bonus. I rebuilt a
**buy-and-hold** equal-weight band portfolio for every (entry date, band) in the HOLD H63 events. Members
come from the same `bandmap` and start on the same entry day. My daily-rebalanced rebuild reproduces
`r_band` (corr 0.9998, mean diff −1 bp), so the comparison is like for like.

| benchmark (HOLD, H63) | validate mean / 63d | t (3-mo blocks) | MDE | years > 0 | rule verdict |
|---|---|---|---|---|---|
| daily-rebal band, net (as shipped) | −1.84% | −5.74 | 0.90% | 0 of 8 | FAILED_VARIANT |
| **buy-and-hold band, net** | **−0.53%** | **−1.68** | 0.88% | 3 of 8 | FAILED_VARIANT (sign branch only) |
| buy-and-hold band, gross | +0.68% | +2.04 | 0.94% | 7 of 8 | CANNOT_DISTINGUISH (design −0.31%) |
| market (FF VW), net | +0.30% | +0.29 | 2.90% | 5 of 8 | **CANNOT_DISTINGUISH** |

- **Bias (daily-rebal minus buy-and-hold), per 63 sessions:** mean +1.49 pp; small band +1.83 pp;
  mid/large/mega +0.22 pp.
- **Bias by year:** 2009 +6.3 pp, 2008 +3.7 pp, 2020 +2.6 pp. The bias is regime-dependent, so it
  also distorts the by-year table.
- **Where 0.8 pp came from.** The note's 0.8 pp is band minus market, which compares two different
  indexes. Buy-and-hold band minus market is −0.65 pp, so the rebalancing artefact is roughly twice
  what was written.
- **The false sentence.** The note says that against the market the verdict is "FAILED_VARIANT either
  way" because design and late are negative. The declared rule does not read design or late for
  FAILED_VARIANT. With validate +0.30% > 0, t 0.29 and MDE 2.90% > worth 0.50%, the rule gives
  CANNOT_DISTINGUISH. I confirmed this with `read_series` on the shipped events.
- **Does the verdict stand?** Yes on the declared net primary, by sign. The economic reading changes:
  validate gross is ~+0.7%, 7 of 8 years, against a ~126 bp round trip. Design and late gross are
  ≤ 0. "Gross ≈ 0, cost kills it" is right; "−1.8% t −5.75" is not.
- **Blocking.** With 6-month blocks the shipped t goes from −5.74 to −4.43. A 63-session hold read on
  3-month blocks overlaps adjacent blocks (protocol item 11). This does not change any verdict, but
  every |t| on the H63 cells is overstated.

### F2 — HIGH — (b) is degenerate by construction, and a 30-second base-rate check would have shown it

- HOLD is 97–99% of events in every year (43,339 of 44,129), which is what Section 16(b) predicts.
  "No sale in 90 days" is the default state, not a conviction signal.
- The cell therefore measured **all insider buys entered 90 days late**. The known insider drift
  lives in the first days or weeks after the Form 4, so the delay discards exactly that.
- The SOLD control (n ≈ 770) has a 6% MDE, so HOLD minus SOLD can never be read.
- **Cost to the record.** This FAILED_VARIANT now sits in the `insider_hold` family posterior as if
  the conviction theory had been tested. Row 3 of the theory table was not tested.
- A declaration gate should refuse a separating variable with more than ~90% of events in one class.

### F3 — HIGH — (c)'s primary is not benchmark-neutral, and "drift slightly improves with the streak" is a composition artefact

- **The declaration's claim.** It says the streak≥3 minus streak-1 difference makes "market and band
  beta cancel". That holds only if the two cohorts have the same band mix. They do not: 74% of
  streak-1 events are small-band in validate, against 59% of streak≥3 events.
- **The bias does not cancel.** The daily-rebalance bias is +1.8 pp in small and +0.2 pp elsewhere,
  so the residual tilts toward streaks by roughly 0.15 × 1.6 ≈ +0.25 pp.
- **Measured.** The validate event-mean difference is **+0.30 pp vs the band** but **−0.28 pp vs the
  market**, so the sign depends on the benchmark.
- **Verdict.** FAILED_VARIANT stands on "no direction found". The note's line "after 2009 it
  slightly improves with the streak, the rival story" should be withdrawn.

### F4 — MEDIUM — The cell answered a different question from the owner's theory (row 13)

- **What row 13 asks.** Its falsifier is "the consecutive-beat cohort's **NEXT** earnings reaction is
  worse (ratchet) or better", plus "subsequent miss probability".
- **What was declared.** The cell declared 63-session post-announcement drift. The next reaction was
  never measured.
- **What I found.** I read it from the shipped parquet. The next announcement is ≤130 days later, the
  CAR is [e−1, e+1] vs the market as shipped, and the window is validate 2009-16:

| streak at t | P(next quarter beats) | next-announcement CAR |
|---|---|---|
| 1 | 60.9% | −0.12% |
| 3 | 69.1% | +0.18% |
| 5+ | 81.4% | +0.36% |

- **Next CAR, 5+ minus 1.** Mean of yearly differences +0.45 pp (se 0.10), 13 of 16 years positive
  over 2009-24. Design 1993-2008 points the same way (+0.51% vs +0.15%).
- **By band.** Small +0.57 pp, mid +0.33 pp, large ≈ 0.
- **The ratchet is real, but partial.** The reward for the next beat shrinks (+2.04% → +1.41%) and
  the punishment for a miss grows (−3.47% → −4.28%). The jump in beat probability outweighs both.
- **How to read this.** It is a post-hoc read by a reviewer, it is not declared, and it sits below a
  ~100 bp round trip. It is a lead for a declared cell, not a finding.

### F5 — MEDIUM — The "reaction shrinks" headline is a point estimate, and it has not been tested against surprise size

The note gives "+2.2–2.9% → +0.9–1.5%" with no interval and no by-year table. I computed both from
the shipped events (mean of yearly differences, 95% CI over years):

| CAR difference | window | mean | 95% CI | years negative |
|---|---|---|---|---|
| 5+ minus 1 | validate | −1.44 pp | [−2.02, −0.86] | 8 of 8 |
| 5+ minus 1 | late | −1.52 pp | [−2.06, −0.97] | 7 of 8 |
| 3 minus 1 | design | −0.50 pp | [−0.70, −0.30] | 15 of 16 |

- **What it survives.** The effect holds within every size band and every spread quintile.
- **What it has not survived.** It has not been tested against the surprise magnitude. Streak beats
  are typically small "managed" beats, and IBES `actual − surpmean` is on disk. Until the reaction
  is shown per unit of standardized surprise, "the market prices the streak in" and "streak beats
  are smaller beats" cannot be told apart.
- **Prior art.** This is close to the meet-or-beat premium literature (Bartov–Givoly–Hayn;
  Kasznik–McNichols). Cite it rather than present it as new.

### F6 — MEDIUM — The family posterior ignores power, which can kill families that are only hard to measure

- **How the posterior counts.** `family_record` adds a full failure for every FAILED_VARIANT and half
  a failure for every CANNOT_DISTINGUISH.
- **The ordering problem.** The verdict rule fires FAILED_VARIANT on `validate mean ≤ 0` *before* it
  checks power. (c) is an example: its validate MDE is 1.20% against an effect worth having of 0.37%,
  and it was still labelled FAILED_VARIANT.
- **The consequence.** For a family whose true effect is small and whose cells are underpowered, each
  cell returns FAILED or CD with near certainty. CANDIDATE needs t ≥ 2, which is rare at low power.
  The posterior therefore drifts down without any evidence against the family. Fewer cells then means
  fewer chances at a positive. That is the self-fulfilling channel.
- **Recovery path in code.** One CANDIDATE lifts `macro_readthrough_commodity` from 0.087 to
  2/12.5 = 0.16 ≥ 0.15. Its weight returns to 1.0 and `_effective_status` re-admits its deferred
  rows. That is adequate on paper.
- **Two gaps in the recovery path:**
  1. Nothing guarantees a shrunk family's admitted row actually gets *run* when the nightly is
     capacity-bound. The quota is ≥ 1, but its EV is multiplied by ≤ 0.58.
  2. Verdicts never decay.
- **The test does not cover recovery.** `test_deferred_rows_return_when_the_family_recovers` only
  re-admits a family with **zero** verdicts (prior 0.2). No test shows failures followed by one
  positive restoring a family.

### F7 — MEDIUM — The shrink can be escaped by renaming, and the quota bypasses policy_state

- **Renaming.** `family` is free text from the generator, and a family with no record gets the full
  base quota. The prompt even prints the shrunk families' names and caps. This chunk already split
  `insider_hold` from `insider_event` (0.18) and created `earnings_streak` and `price_location`.
- **Two levers, one of them outside policy_state.** Only the EV multiplier goes through the declared,
  bounded, journaled `policy_state` key. That part is a preference, not a kill, as claimed. The
  generation quota (`family_budget`) is computed from the posterior plus config constants, outside
  `policy_state`. The stronger of the two levers is code, not a preference.
- **Fix.** Use a fixed family taxonomy, or map new labels onto existing families by cosine before the
  quota applies.

### F8 — MEDIUM — The duplicate rule is not enforced by code, and a re-read counts as a fresh failure

- **What is good.** The hi52 declaration states honestly that it is a re-read with search count +0.
- **What the code does.** It has no check:
  - `ledger_row` → `L.append` skips `dedupe()` (the ledger rows carry `dedup: None`).
  - `dedupe()`'s corpus is TRIALS plus two closed docs. It does not include the library rule receipts
    (`library_rules_LIB_*.jsonl`), so the name `hi52` would never be caught even on the generator
    path.
- **The double count.** The re-read adds a full FAILED_VARIANT to `price_location`'s posterior. "+0"
  in prose is +1 in the posterior.
- **Fix.** Make a cell whose rule name or feature appears in a library receipt either refuse, or
  declare `reread_of: <receipt>` and be excluded from the posterior.

### F9 — LOW — The declarations are honest, but they are tamper-evident only locally

**What checks out:**
- The declarations were written at 16:06:32/32/33 UTC. Results followed at +7 s, +39 s and +16 min.
- The ledger's tracked `DECLARED` rows carry the same timestamps.
- The current script reproduces all three declaration hashes, and the hi52 input shas still match.
- Every primary metric, window, threshold and reported block in RESULTS is named in its declaration.

**What does not:**
- All six JSON receipts are **untracked**, and nothing was committed between declare and run.
- A self-hash inside the same file proves internal consistency, not timing.
- Commit the declaration (or push its hash) before `run`.

### F10 — LOW — Units are mislabelled

- **Monthly values that are not monthly.** For (b) and (c), `mean_monthly` is the mean *per 63-session
  event return*, grouped by entry month. The note writes (c) as "−0.48%/mo"; it is −0.48% per 63
  sessions. MDEs are in the same unit.
- **By-year values.** `primary_by_hold_year` sums 12 overlapping cohort means, which is how "2008:
  −75.7%" appears for (b). Those magnitudes are meaningless. Print by-year *means*.

### F11 — LOW — Smaller construction points

- **Entry-day mismatch.** The event leg runs open-to-close on the entry day, while the benchmark is
  close-to-close and includes the entry-day overnight.
- **Delisting.** An event that delists inside H is dropped, not marked to its delisting return.
- **Sign convention.** hi52 uses `sign: +1` while beat_streak uses `sign: design`. Under `design`,
  hi52 would read CANNOT_DISTINGUISH. The declared choice is defensible, but the policy should be
  stated once for all cells.
- **hi52 itself.** Its verdict is unaffected by the band bias, because it is read against a monthly
  fair twin. It stands as written.

---

## Tests (item 6)

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_hyp_lab_family_budget.py \
  backend/tests/test_hyp_theory_cells.py backend/tests/test_hyp_lab.py backend/tests/test_policy_state_is_read.py -q
........................................................................ [ 90%]
........                                                                 [100%]
80 passed in 9.35s
```

**Mocks:**
- `test_hyp_lab_family_budget`:
  - `PS.STATE_PATH` and `PS.JOURNAL_PATH` point to tmp.
  - `L.LEDGER`, `L.RECEIPTS` and `L.REPO` point to tmp.
  - `S.HL.call` is replaced by `fake_call` (no LLM).
  - `L.dedupe` is the identity.
  - `HC.bar_symbols` is stubbed.
- `test_hyp_theory_cells`:
  - `T.OUT` and `L.LEDGER` point to tmp.
  - The RAM probe and sleep are injected.

**Not tested at all:** `event_returns` / `_measure` (the benchmark construction behind every (b)/(c)
number), `monthly` units, band composition per cohort, the HOLD base rate, recovery after failures,
and family renaming.

---

## Item 7 — the owner's 13 theories: the next $0 night, and what is not a hypothesis yet

**Next $0 night, in order:**

1. **Row 13, done as written.** Declare: P(next beat) and next-announcement CAR by streak, controlling
   SUE and size band. Include a tradeable "hold into the next announcement" leg: enter at e−2 close,
   exit at e+1, net of the round trip. F4's read is post hoc, so declare it as a re-test. Design and
   validate have both been seen, so the decision slice must be one nobody has looked at: pre-1993
   IBES if `surpsum` reaches that far, else a forward shadow.
2. **Row 3, rebuilt point-in-time.** Define the buyer as a *habitual non-seller*: zero open-market
   sales in the prior 24–36 months, knowable at t. Enter at Form-4 public date +1, versus routine
   buyers, against a buy-and-hold band. Cite `insider_opportunistic` (Cohen–Malloy–Pomorski) as the
   nearest corpse first; if it already conditions on this, the cell is a re-read.
3. **Row 8 (continuous oil → E&P) and row 10 (China/EM → multinationals)** on `macro_lead_lag`. They
   are cheap, but the same cell type found no lag twice, so expect low P(changes roadmap). Run them
   only after 1–2.

Row 11a (prediction-market move as a lead-lag sensor) is legitimate to test. Its scoring-path bar
stays in force whatever it shows.

**Not a hypothesis yet.** For each row below, nothing observable beforehand separates it from factor
or sector beta:
- **Row 1, "successful founder".** "Successful" is defined by the outcome. That is the winner
  explained afterwards.
- **Row 7, rare earths / robotics demand.** The precursor is commodity momentum, which is a factor.
- **Row 9, GLP-1 supply chain.** The universe would be hand-curated after the winners are known, and
  the mechanism class is already dead at the next session.
- **Rows 4 and 5, "regime-supported" and lobbying.** These need a precursor that separates them from
  defense/sector beta before data is worth pulling.
- **Row 8's Venezuela-specific half.** Already flagged by the builder as needing a tagger.
- **Row 2, monopoly.** Already closed against the market. Only a margin-*stability* plus
  concentration variant would be new.

---

## Three things I would have done instead

1. **Benchmark first.** Event studies should use a buy-and-hold, characteristic-matched portfolio
   formed at entry (band, or band × book-to-market × momentum, DGTW-style). Every difference design
   should print the band mix of each cohort, so the benchmark could not have moved (b) by ~1.3 pp or
   flipped (c)'s sign.
2. **A base-rate and power gate at declaration.** Before hashing, print:
   - the share of events in each class of the separating variable (refuse above ~90%);
   - the control-cohort n and its MDE;
   - whether the declared primary is the theory row's own falsifier.
   (b) and (c) would both have been redesigned before running.
3. **A posterior that learns from evidence, not from noise.** Count only powered negatives
   (validate MDE ≤ the effect worth having) as failures, and count CANNOT_DISTINGUISH as zero. Decay
   old verdicts. Allocate generation by Thompson sampling or UCB rather than the posterior mean, so an
   uncertain family keeps being explored. Map family labels onto a fixed taxonomy so a family cannot
   escape by renaming, and make a re-read of a library rule carry zero weight.
