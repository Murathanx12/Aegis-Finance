# FINDING — 2026-09-06 — ERA REPLAY v2: the blind held, and the model cannot read

**Job:** L10 / CONTINUATION §2b — the LLM reading test, decide step, 2016-19 era.
**Licence:** `PRODUCT_EXPERIMENT` (exploratory). A screen cannot reach NOVEL.
**Receipts:**
`backend/data/optimus/continuation_2026-09-06/L10_era_replay_v2_run01.json`
`backend/data/optimus/continuation_2026-09-06/L10_era_replay_windows.json`
`backend/data/optimus/continuation_2026-09-06/L10_era_replay_v2_pilot.json`
**Code:** `scripts/era_replay_v2.py` · **Tests:** `backend/tests/test_era_replay_v2.py` (26)
**Cost:** **$0.48** of a $5.00 mandate — $0.3032 gpt-5-nano (telemetry), $0.1785
DeepSeek (estimate; provider balance $9.81 → $9.39 across a SHARED key).

---

## 0. RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE. VERDICT: NOISE.**

All four arms lose to the equal-weight basket of the same eight names. Rank IC is
negative in all four. No arm survives BH-FDR. No arm is distinguishable from
ranking the same bundle at random.

**But the experiment is not a null result about nothing — three things it
establishes are worth more than the arms table:**

1. **The blind held completely.** 0 of 768 decisions named the true year. This
   is the first time the fantasy-transposition blind has been measured on a
   pre-2023 era, which is where every model knows the ending.
2. **When blinded, `deepseek-chat` assumes it is 2023-24.** Of the 243 windows
   (of 768) where it guessed a year at all, **190 said 2023 and 53 said 2024 —
   not one said 2016, 2017, 2018 or 2019.** It is not identifying the era; it is
   applying its own recency prior to a cross-section from eight years earlier.
3. **The diary suppresses the canary.** With a diary the model declines to guess
   in 191 of 192 windows; without one it declines in 93 and 50. So the canary is
   *weaker evidence in the diary arms*, and any future era replay must ask the
   canary in a separate call rather than assume it is free.

---

## 1. THE 2×2

192 windows (4 threads × 48 months of 2016-01…2019-12), 8 names per window,
top-3 held, 10 bps per side on realised turnover, benchmark = the equal-weight
basket of the **same eight anonymised names in the same month**.
`n_effective` = **48 month blocks**, not 192 windows.

| arm | mean IC | t(IC, blocks) | net vs EW %/mo | t(blocks) | TW book | TW EW | ratio | canary |
|---|---|---|---|---|---|---|---|---|
| `fantasy_nodiary`  | −0.0314 | −0.96 | **−0.393** | −1.05 | 1.549 | 1.939 | 0.799 | 0.000 |
| `fantasy_diary`    | −0.0259 | −0.81 | **−0.127** | −0.35 | 1.759 | 1.939 | 0.907 | 0.000 |
| `realanon_nodiary` | −0.0459 | −1.34 | **−0.353** | −1.00 | 1.577 | 1.939 | 0.813 | 0.000 |
| `realanon_diary`   | −0.0531 | −1.58 | **−0.530** | −1.39 | 1.459 | 1.939 | 0.752 | 0.000 |

Every terminal-wealth ratio is below 1. The best arm loses 0.13%/month.

**Neither axis has a consistent sign.** The diary helps fantasy (−0.393 →
−0.127) and hurts real-anon (−0.353 → −0.530). Real-anon beats fantasy without a
diary and loses to it with one. At 48 blocks these are the differences of four
draws from the same distribution, and saying anything else about them would be
reading the noise.

## 2. THE NULLS (vision §3d)

The raw excess is **not** the right statistic here: a top-3-of-8 book pays
turnover the equal-weight basket does not, so a book that ranks at random
already shows about **−0.20%/month**. Null 1 is the test that matters.

| arm | N1 shuffled companies (mean, p) | N2 shuffled dates (mean, p) | N3 same-day paired (top−bottom, t) |
|---|---|---|---|
| `fantasy_nodiary`  | −0.204%, p 0.72 | −0.167%, p 0.75 | −0.449%, t −0.68 |
| `fantasy_diary`    | −0.200%, **p 0.41** | −0.189%, p 0.42 | −0.293%, t −0.44 |
| `realanon_nodiary` | −0.201%, p 0.68 | −0.158%, p 0.73 | −0.601%, t −0.93 |
| `realanon_diary`   | −0.198%, p 0.85 | −0.157%, p 0.87 | −0.772%, t −1.19 |

Read plainly: **three of four arms rank worse than chance**, and the fourth
(`fantasy_diary`, p 0.41) is indistinguishable from chance. Null 3 — chosen
versus not-chosen inside the same bundle in the same month, where the month
effect cancels exactly — is negative in all four and significant in none.

## 3. INFERENCE (`learner/inference.py`, best arm `fantasy_diary`)

- family size **4**, family-max p **0.729**, family-min p **0.173**,
  BH-FDR: **nothing survives at 0.05**
- **DSR 0.0805 — `WITHIN_SELECTION_NOISE`.** After four cells, a zero-edge search
  is expected to produce SR 0.153; this arm's is −0.050.
- **SPA p 1.000 — `WITHIN_SPA_NULL`.** No arm in the family has positive expected
  paired excess.
- **PBO 0.386 — `SELECTION_IS_FRAGILE`.**
- **MDE: 8.75%/yr.** On the 4.0 years this era holds, the smallest annual excess
  an arm could have shown at t = 2 is 8.75%/yr.

**So "NOISE" means "not detectable on four years", not "absent".** An LLM edge
of, say, 3%/yr would need ~34 years of this design to reach t = 2 and is
invisible here by construction.

**Three-era sign table: CANNOT DETERMINE.** `learner.evaluate.ERAS` is
2016-18 / 2019-21 / 2022-24 and this job ran 2016-2019 only. The year-by-year
signs inside the era flip in every arm (fantasy_nodiary − − + −;
realanon_diary − − − +) and are not a substitute for it.

## 4. WHAT WAS REFUSED, AND WHY

**The EDGAR 8-K item tape was excluded from the bundle.** Its own
`manifest.json` says the universe is resolved through `company_tickers.json` =
**current registrants**, so a name's having 8-K rows in 2016-19 correlates with
surviving to 2026 — a forward-looking leak straight into the prompt. The same
manifest's `coverage_truncation_caveat` is the second reason: absence there is
truncation, not evidence. Including it would have made the bundle richer and the
test wrong. The refusal travels in the window receipt, not only in this doc.

**The correction the brief asked me to verify: CONFIRMED.**
`docs/CONTINUATION_2026-09-06_OPUS_PROMPT.md` §2b says *"Friday's L10 built the
scaffolding"*. It did not. `docs/BUILD_NIGHT_LAB_2026-09-05.md` §5 lists L10
among the jobs **not run**, and `backend/data/optimus/night_lab_2026-09-05/`
holds L1, L4, L8, L11, L12, L13 and no L10. The v1 machinery exists but lives in
the **sibling** repo (`aegis-alpha-terminal/alpha/transpose.py`,
`scripts/era_replay.py` — $0.30, 150 windows, 11 rebalances, k=5). v2's diary
arm, nulls 2 and 3, and the canary as a coded control existed nowhere. This
session built them.

## 5. THREE DEFECTS THE PILOT FOUND, ALL OF WHICH WOULD HAVE FAILED SILENTLY

Each cost real money to find and each is now pinned by a test.

1. **`deepseek-chat` abbreviates "Company A" to "A".** The first pilot lost
   **every single real-anon window** to a validator that reported only
   *"rank is not a permutation"*. Two arms of a 2×2 were empty and the run still
   printed a table. `normalise_rank` now maps the abbreviation and still refuses
   anything ambiguous.
2. **`gpt-5-nano` keys its JSON on the whole heading line**
   (`"Company A -- sector Manufacturing, size bucket small."`), not the label.
   That threw away 11 of 20 bundles as *"rewriter omitted a label"*.
3. **The magnitude gate was measuring itself.** Its first version regexed the
   whole card and counted the FIELD NAMES — "12-1 momentum", "4 weeks", "60d
   volatility", "rating 3.33 **of 5**" — as data the rewriter had failed to
   reproduce, and scored a faithful rewrite at **0%**. Checked against the actual
   emitted values, preservation is **97.9% (fantasy) / 98.4% (real-anon), gap
   0.005**, and the leak check is clean on 384 of 384 bundles.

Point 3 matters beyond bookkeeping: **the arm-preservation gap is the number
that decides whether the 2×2 means anything at all.** If the rewriter kept
materially more of one arm's card than the other's, the fantasy-vs-real-anon
contrast would be measuring the rewriter and not the decider. At a gap of 0.005
it is not. A teammate reading the broken 0%-preservation pilot reasonably called
it the session's headline finding; the honest version is that the *checker* was
broken, and the rewriter is faithful.

## 6. WHAT THIS DOES AND DOES NOT LICENCE

**Does:** the blind is now a measured instrument on a pre-2023 era, reusable at
$0.0025/window. The scaffolding — windows, diary threads, three nulls, canary,
integrity gates, budget governor — is built and tested.

**Does not:** any claim that "LLMs cannot read". One decider, one prompt, one
era, one horizon, one bundle size, 48 month blocks, and an MDE of 8.75%/yr. The
result is that **this** decider, given **this** blinded numeric situation, does
not order next month's cross-section better than chance.

**The most informative single line for the next session** is not the arms table.
It is that a blinded frontier model asked what year it is answers *2023* with
near-unanimity, and that giving it a diary makes it stop answering at all.

## 7. NEXT, IN ORDER

1. **Ask the canary in a separate call.** It is nearly free and the diary arms
   showed the in-band version is suppressed by whatever else the model is asked
   to write.
2. **Give the decider something the tape does not already have.** This bundle
   was 13 panel numbers per name — exactly the information `learner/` already
   models better. The vision's premise was *company voice* (8-K exhibit 99.1
   press-release text), and that requires fixing the survivorship defect in the
   8-K universe first, which is a data job, not an LLM job.
3. **Do not re-run this design for power.** At MDE 8.75%/yr on four years, the
   binding constraint was never money — the run used $0.48 of $5.00. It was
   independent months, and the other two eras are the only cure.
