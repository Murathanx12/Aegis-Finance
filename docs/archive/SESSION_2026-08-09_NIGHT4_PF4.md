# SESSION 2026-08-09 (night) — NIGHT-4 / PF-4: taking the winner apart

Branch `factory/night-4` in the `Aegis module` repo. `aegis-finance` on `main`.
No lane seeded, no flag flipped, `paper_nav` untouched, no key changes,
**holdout unread** (`allow_holdout=False` throughout, every artifact carries
`holdout_read: false`).

Four external adversarial reviews were adjudicated at home. Three of their
attacks landed; this night acted on all of them, and the answers were not the
ones anyone predicted — including me.

---

## The short version

1. **The reviewers' central hypothesis is wrong.** The +4.67 %/yr is *not* the
   equal-weight rebalancing premium: the equal-weight eligible universe's own
   alpha is +0.78 % at t 1.08, and its raw excess is **negative**. The
   incremental contribution of selection is **+4.23 %/yr at t 3.65**. Frozen
   rule → **CONFIRMED**.
2. **And their conclusion is right anyway, by a different route.** Against a
   properly built small-cap profitability factor, the alpha collapses from
   +5.01 % (t 3.39) to +2.98 % (t 1.87), and the incremental from +4.23 % to
   **+1.04 % (t 1.07)**. The book is small-cap profitability, honestly named — a
   factor harvest, not a discovery. It may never again be called a new factor.
3. **The margin was in implementation, not in the signal.** Annual rebalancing
   under era-appropriate costs beats the registered monthly/flat-25
   configuration on *every* axis: t 2.69 vs 2.52, post-2001 excess +6.21 % vs
   +5.94 %, turnover 0.48 vs 2.40, cost drag 31 bps vs 120, max drawdown −48.4 %
   vs −52.5 %, incremental alpha t **4.50** vs 3.65. It is also the only version
   a person could hold.
4. **The product question, finally asked.** Against Ken French SMALL HiOP — the
   long-history proxy for a buyable small-cap-profitability fund, *gross* of the
   costs we pay — the shippable configuration adds **+2.03 %/yr at t 1.13**
   (2.04× terminal wealth over 40 years, shallower drawdown). Real, and not
   statistically distinguishable from zero even with forty years of data.
5. **We retracted our own headline.** NIGHT-3's "membership not ordering" is
   withdrawn.
6. **We found our own memory control was an outlier seed.**

## What was retracted

`Aegis module/docs/RETRACTION_NIGHT3_5_2_2026-08-09.md`.

Within-slate ordering is **unmeasured below ~6.2 %/yr** — point +1.68 %, 95 % CI
[−4.39 %, +7.75 %], t 0.54 — not zero. The oracle bracket, which should have been
printed beside it all along, shows perfect foresight is worth +205 %/yr on the
same slate: **ordering information exists in abundance**; what was unmeasured is
how much the composite captures.

And the structure the test was blind to: splitting the slate into quartiles of
composite rank gives an **inverted U** — ranks 11-20 carry +8.93 %/yr at t 2.38
while ranks 1-10 carry −1.17 %. A top-20-minus-bottom-20 spread averages q1+q2
against q3+q4 and cancels almost exactly. Recorded as a **hypothesis, not a
finding** (q2 is the best of four comparisons and does not clear Bonferroni).

**The LLM re-ranking campaign is un-cancelled.** It was cancelled on a null that
could not support the decision.

Scored against the house: a **process miss**. `POWER_CHECK.json` already
contained the correct reading — "the verdict must be UNRESOLVED, not REJECT" —
and the house did not follow its own sentence. The ledgers could not catch it,
because it is an inference failure, not an integrity failure. That is the most
useful thing the review surfaced.

## What the reviews got right, and wrong

Registered before compute, scored after.

| claim | outcome |
|---|---|
| delisting 0 % assignment is an upward bias | **direction right, magnitude wrong by an order of magnitude** — 2,523 names imputed at −30 %, effect **−0.01 %/yr**. Their −0.1…−0.4 % missed; the house's own ≤0.3 % was also far too large |
| flat 25 bps is wrong pre-decimalization | **right, and it matters most** — tick floor median 54.3 bps pre-1997; pre-2001 excess falls from ~5.0 % to **+1.31 %** |
| the EW rebalancing premium explains it | **wrong** — +0.78 % alpha, t 1.08 |
| RMW is the wrong benchmark | **right, and decisive** — the correct benchmark absorbs almost everything |
| the 1982 start is a researcher degree of freedom | **wrong, and worse** — it is a never-inflation-indexed $200k nominal dollar-volume floor. In 1963 only 215 names in all of CRSP clear it, all large caps, so the small segment is empty by construction. It silently costs **every** small-segment strategy 19 years of panel |
| the memory placebo rests on one seed | **right** — the seed used was above all six new draws |
| pre-registration is self-attested | **right, and now closed** — registry SHA-256 anchored to Bitcoin via all four OpenTimestamps calendars |
| no independent reimplementation | **right, and now closed** — see below |
| multiple testing is per-campaign | **right, and now closed** — programme-wide denominator auto-attaches to every scorecard |

## Three things now built that did not exist

1. **Independent reimplementation** (`scripts/pf4_independent_reimpl.py`) —
   imports nothing from `aegis_brain`, re-derives eligibility, segment,
   composite, and pivots the OSAP long frame with plain `pivot_table` instead of
   the preallocated scatter that is the one place a silent (month, permno)
   misalignment would be fatal and invisible. Result over 482 months:
   **max absolute monthly difference 0.0**, correlation 1.0, CAGR gap 0.000 pp.
   Caveat recorded with it: this rules out coding error, not a shared
   conceptual error, since both obey the same timing and NaN conventions by
   design.
2. **The accumulating constraint ledger** (`aegis_brain/pf/ledger.py`) —
   Murat's "a system where every run the engine picks up, learns and improves",
   built so that what accumulates is **constraint, not parameters**. Every
   scorecard now carries the programme-wide denominator (**821 tests**) and the
   bars it implies (Bonferroni 4.01, BHY 4.46, HLZ 3.0); runs append to
   `ledger/pf_runs.jsonl` with commit and denominator; a family with 5+ prior
   variants gets a loud warning on every new scorecard. The engine gets *harder
   to fool* each run, which is the only version of "learns" that survives
   contact with the evidence.
3. **Gate power, printed for the first time** — G2's binary read discards a
   *true* +4.67 % strategy 29.5 % of the time (56 % against the +3 % bar with
   the disclosed headwind); G9's false-negative rate at a true +2.5 % effect is
   43.4 %. Both worse than the reviewer estimated.
   `AMENDMENT_G2_HOLDOUT_GRADED_READ.md` re-specifies the holdout as a graded
   likelihood-ratio read with frozen thresholds — registered **before** G7
   exists and **before** the holdout is read. Sequencing unchanged: G7 first,
   attended, Murat present.

## Which statistic we stand on

At 821 programme-wide tests:

| statistic | value | HLZ 3.0 | Bonferroni 4.01 | BHY 4.46 |
|---|---|---|---|---|
| headline excess t | 2.52 | ✗ | ✗ | ✗ |
| FF5+UMD alpha t | 3.39 | ✓ | ✗ | ✗ |
| **annual config incremental alpha t** | **4.50** | ✓ | ✓ | ✗ |

One number against the "you are noise mining" reading: at 821 tests an
unadjusted 5 % screen would produce about **41** apparent discoveries on pure
noise. We have declared **one**.

## Open for Murat

1. **One dependency, and it is the product question:** a PIT-clean ETF price
   feed (Polygon or FMP) for AVUV, DFSV, IJS, VBR from 2019-09. Without it the
   comparison against the actually-buyable alternative stays a French-portfolio
   proxy. This is the only thing this campaign needs from you.
2. **The shippable configuration changed.** Annual rebalance, era-appropriate
   costs. G7's first workload should be that, not the monthly spec.
3. `factory/night-3` is still unmerged; `factory/night-4` is a new branch on top
   of the same base. Both await your read.
4. Signal work is now deprioritized relative to implementation work — this
   campaign moved the product by changing *when we trade*, not *what we pick*.

Full verdict: `Aegis module/docs/PF4_VERDICT_2026-08-09.md`.
