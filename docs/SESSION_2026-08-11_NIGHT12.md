# NIGHT-12 — his record, measured; and the first thing that survived its short leg

**2026-08-11.** Murat disclosed his own investing record and asked the programme
to learn from it. Five phases ran. Two produced real findings, three produced
honest nulls, and the nulls are the ones with the most decision value.

Commits: `d99f5ba` `eb97949` `3f6cde1` (aegis-finance) · `3a6aa17` (Aegis module).

---

## The headline

**1. The revision family SURVIVED its short leg — the first thing in this
programme that has.** Round 16 measured 88–99.9% of a comparable spread living
in the leg a long-only book cannot hold, and NIGHT-11 registered this as the
cheapest test that could kill the family. It did not kill it. The short-leg
share is **41.8–52.1%, median 47.2%**, and the long leg alone clears its own MDE
in **6 of 7** licensed arms.

**2. His selection cannot be distinguished from his own watchlist, and the
design says so honestly.** +1.6 points against an MDE of 80. That is not a
finding about his skill; it is the instrument stating its limits.

---

## 1. CONVICTION-REPLAY-1 — did the judgment or the spreadsheet do the work?

His sheets record **both his picks and the pool he drew them from, priced the
same day**, which is what makes the question identified instead of a story.

Measured 2025-11-07 → 2026-08-10, equal-weighted, from actual closes:

| | return | n |
|---|---:|---:|
| **his 13 picks** | **+34.6%** | 13 |
| **his 48 non-picks** | **+33.0%** | 48 |
| difference | **+1.6 pts** | p 0.959 |
| **measured MDE at 80% power** | **80 pts** | |
| top-13 by his sheet's analyst upside | +51.2% | real ranking |
| the 14 names rated 5.0 by consensus | +78.6% | *not a ranking* |
| SPY / QQQ / IWM / XBI / SMH | +16.2 / +18.7 / +25.1 / +45.7 / +64.1 | |

**Verdict: `UNRESOLVED_ABSENCE_OF_EVIDENCE`.** 13 names over one nine-month
window cannot resolve a selection edge of any plausible size. Under CANON §19
this may **not** be recorded as a finding that he has no skill. The MDE is
measured by planting effects of known size, never derived from a formula.

The sign is worth noting without being promoted: his picks trailed the
sheet-upside rule, the consensus group, XBI and SMH — but every one of those
gaps is far below the MDE too.

### Three defects, each of which changed a number

**APLT and SLNO were silently excluded.** Both delisted by cash takeover; no
free feed carries one surviving bar for either. Carrying the payout was not
enough — with no entry price they still had no computable return and were
dropped. APLT is his **worst** position (−89%, taken out at $0.088 plus a
non-tradeable CVR marked at zero) and SLNO a **watchlist winner** (taken out at
$53 from a sheet price of $43), so the two errors **compound rather than
cancel**, both flattering the answer. Including them moved the difference from
**+11.7 to +1.6 points**. Their entry prices come from his own sheet — a weaker
source than every other name — so the result is reported both ways.

**The exit annotations attached to the wrong positions.** The wrapped
`(sold at X)` line attached to whatever row parsed last, putting ALMS's exit
price on DKNG, which was never sold; and stripping the annotation greedily ate
the price columns, dropping all three sold positions from the January book.

**"Top 13 by consensus rating" was not a ranking.** Fourteen names sit at
exactly 5.0 with **none strictly above**, so it was thirteen drawn from a
fourteen-way tie — ties printed as a ranking, the NIGHT-10 defect again. Now
reported with its tie-break range: **+47.6 to +87.9**.

### His three self-diagnosed failures, measured

**Exits — the registered prediction held: the sign is NOT uniform.**

| | entry | sold | at 2026-08-10 | cost of selling |
|---|---:|---:|---:|---:|
| ALMS | 4.5 | 10.0 | 27.53 | **+390 pts of entry** |
| TVTX | 34.0 | 34.4 | 60.89 | **+78 pts** |
| SLDP | 8.5 | 8.1 | 2.35 | **−68 pts (a good exit)** |

The TVTX exit is the instructive one. At the January sheet it looked *right*
(sold 34.4, then 22.8). By August it had cost 78 points. An exit graded at one
date and an exit graded over a horizon are different measurements.

**Capture — the asymmetry, not the beta, is the problem.** His picks captured
**2.31× the upside and 2.48× the downside** (beta 2.15). His non-picks:
**2.00 / 1.83**. His description — "they drop much more, but when the market is
up they make much more up" — is right about both magnitudes and wrong about the
ratio. Up/down is **0.93** for his picks and **1.09** for the names he passed on.

**The rebalance was an independent second draw, and it went the wrong way.**
Between the sheets he promoted 6 names and demoted 5. From 2026-01-13:
**promoted −2.5%, demoted +32.5%** (p 0.37, n 6 vs 5 — not resolvable).

### What this cannot do

It cannot produce his NAV. The sheets carry no share counts, no cash and no
transactions. **The +73.7% vs "2025 +115%" gap is NOT reconciled** and nothing
is trained on either. Worth stating plainly: an equal-weighted buy-and-hold of
his November book returned **+34.6%** over nine months against his reported
+73.7% over twelve — so most of his headline came from **weighting, trading, or
the months before the sheet**, and which of those it was cannot be settled
without the transactions.

---

## 2. COUNTERFACTUAL-EXITS-1 — the leakage-free half of the laboratory

Every position, every month-end, branched seven ways and rolled forward on real
prices. No model is involved, so the CANON §13 leakage problem does not arise.

| branch | mean terminal value per dollar |
|---|---:|
| hold | **1.166** |
| sell to benchmark | 1.129 |
| rotate to best momentum | 1.111 |
| **sell to cash** | **1.000 — never the best branch in 60 rows** |

Going to cash was never right here. One bull window, and reported as such — but
it is the direct mechanical answer to "I should have sold and sat liquid."

**The SOC question comes back `NO_OBSERVABLE_SEPARATES_AT_THIS_SAMPLE`.** The
leading candidate, `drawdown_from_peak`, correlates **+0.64** with
hold-minus-sell at **p 0.021** against an **MDE of 0.80** — significant *below*
its own MDE, which is precisely the winner's-curse region §19 refuses to promote
from. Its sign points the opposite way to the take-profits instinct: names
nearer their highs kept winning.

Two defects in my own reporting, fixed: `trim_*` and `take_original_out` are
convex combinations of hold and cash and can **never** win a maximum, so "best
in 0 of 60" was a theorem reported as a result; and `pct_of_peak` is
`1 + drawdown_from_peak`, the same feature counted twice. Inference permutes
across **names**, not rows — 60 rows are 12 names viewed six times on one path.

---

## 3. The spine — BeliefState and PredictionRecord, frozen; the clock started

The blocker on a two-way Optimus was never the read-only MCP. It was that there
was **no shared object to talk about**. Both schemas are now frozen, with the
Murat-style fields his process ran on (`theme`, `causal_chain`,
`adoption_stage`, `catalyst_timeline`, `scenarios` as a probability tree,
`payoff_skew`) **and the two it was missing**: `thesis_breakers` and
`next_observable`. Holding NTLA "waiting for 26 again" is an anchor, not a
thesis, and an anchor cannot be falsified because it claims nothing about the
world.

Two of the four observables describe the **shape** of the payoff rather than its
direction. `abs_move_exceeds` is how a binary-catalyst biotech states a
probability tree in a form the engine can score — the object the reviews
correctly said this machinery could not evaluate.

**First live run: 87 predictions from 5 DeepSeek specialists over 31 of his own
names.** Effective distinct ideas **66 of 69** in the first batch (CANON §20 —
NIGHT-10 found ten "independent" LLM hypotheses that were one connected
component; this batch is genuinely diverse). Nothing resolves yet; the shortest
horizon is 5 trading days. That is the point.

**`ANTHROPIC_API_KEY` is still empty.** The `.env` line carries a trailing
comment, so a length check reports 79 characters and a live call fails. Verified
by calling, not by measuring a string.

**A defect the run produced and the ledger caught:** six forecasts arrived with
thresholds in **percent** — `|move| > 20.0` is a 2000% move — and **all six came
from one specialist**. At p=0.75 that is a guaranteed-wrong record charged to a
forecaster whose judgment had nothing to do with it. `make_prediction` now
refuses any threshold ≥ 1 rather than coercing it, and the six are **voided in
place**: kept as evidence the forecast was made, excluded from every score.
Deleting them would hide a defect; grading them would charge for one.

---

## 4. EXPOSURE-CONTROLLER-V0 — it never fired, and that is the finding

`ExposurePolicy` **refuses to construct** without a minimum dwell and a re-entry
band above its de-risking threshold, because a controller with no re-entry looks
fine in every backtest that ends during the drawdown.

It never left `risk_on`. SPY held above its 200-day average all window and
realised vol never reached 1.5× its one-year level, so the overlay cost nothing
and saved nothing.

**What that implies is the useful part.** His book drew down **22.9%** while SPY
drew down **8.9%**, at beta **2.15**. His drawdown was mostly his own beta
amplifying a shallow dip that no market-regime trigger would fire on. **His
third self-diagnosed failure is not primarily a market-timing problem in this
window — it is the cost of carrying 2.15 beta**, which is a sizing question a
market-keyed controller cannot answer.

The policy was **not** loosened until it fired. Tuning a trigger on the one
sample it is tested against is fitting the rule to its own test.

---

## 5. REVINFO-1's short leg — the family survives

| arm (small caps) | spread | **long leg** | MDE | t | short-leg share |
|---|---:|---:|---:|---:|---:|
| `tgt_rev_breadth` h1 | +9.36 | **+4.48** | 3.21 | 3.91 | 52.1% |
| `tgt_rev_breadth` h3 | +7.32 | **+3.95** | 2.79 | 3.96 | 46.1% |
| `eps_rev_breadth` h1 | +6.64 | **+3.24** | 2.57 | 3.53 | 51.2% |
| `eps_rev_breadth` h3 | +5.54 | **+3.08** | 2.26 | 3.82 | 44.5% |
| `eps_rev_breadth` h6 | +4.66 | **+2.72** | 2.19 | 3.47 | 41.8% |

The top decile alone earns **+3.44 to +6.48 %/yr at t 2.88 to 5.45**.

Under CANON §18 the claim that one leg carries more than the other is a claim
about their **difference**, estimated from the paired monthly series with its
own SE — never read off the share, which has none. **It is not detectable in any
of the 7 arms** (|t| ≤ 1.04 against MDEs of 2.1–4.3), so the honest reading is an
even split and the ~47% is descriptive only.

**Still Layer 1 and still gross.** ANALYST-IBES-1 measured this family dying at
10× turnover. Surviving the short leg says nothing about surviving costs. It
licenses a Layer-2 decision-boundary test for a long-only book and nothing else.

---

## 6. What was deliberately not built

The market episode store, portfolio gym, historical LLM simulation, evolution
engine and teacher library. Reasons unchanged and now partly evidenced: the
leakage-free core of that vision is the mechanical counterfactual engine, which
**was** built; and the false-discovery bar scales with pool size, so a bigger
genome pool over the same information set is a more expensive null.

## 7. Still owed by Murat

cash · rulings on five kill conditions (ABSI/AMSC/HUBS/KYTX/SLDP) ·
`confirmed: true` · **a real `ANTHROPIC_API_KEY`** (still absent — verified by a
live call) · seeding the shadow books · the graceful-degradation ruling.

## 8. Next, in order

1. **The transactions.** They are the only thing that can reconcile +73.7% vs
   +115% and separate his selection from his sizing. Everything about his record
   is limited by their absence, not by instrument power.
2. Layer-2 decision boundary for `eps_rev_breadth` small — the long leg survived,
   so this is now the highest-value test in the registry. **Accrues.**
3. A drawdown trigger keyed to the BOOK's own path rather than the market's,
   pre-registered before it is tuned.
4. Resolve the first PredictionRecords at h=5 and h=20; report calibration with
   its count beside it.
5. The revision family's turnover through G7 — the cost question the short-leg
   result does not touch.
