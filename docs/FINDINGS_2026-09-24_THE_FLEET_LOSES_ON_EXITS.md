# 2026-09-24 — four hypotheses tested overnight, three refuted, one worth money

Everything here is measured from the venue or from panels on disk. **LLM spend
$0.00.** The 10-hour simulation ran alongside and is unaffected by any of it.

---

## RESULTS SCOREBOARD

| line | state |
|---|---|
| best historical net strategy vs market | **none** — §59 stands, and horizon extension does not rescue it |
| best forward paper strategy | fleet **$452,856 of $500,000, −9.4%**; another **−$9,084 overnight** |
| new actionable finding | **a −2% stop would have saved 75% of the fleet's realised loss** |
| hypotheses killed | 3 of 4 (capacity, stale positions, friction) |
| LLM spend | **$0.00** |

---

## 1. Where the fleet's money actually went

| | |
|---|---:|
| drawdown | −$47,307 |
| unrealised (what it HOLDS) | **−$905** |
| realised (what it CLOSED) | **−$46,401** |

**98% of the loss is realised.** The books are not bleeding from positions they
hold; they bleed from trading.

### Three hypotheses, all refuted

**"The books cannot rotate — old positions hold the gross budget."** No. Max
gross is 88% (hack6), fleet average 39%, and only 8 of 20 positions exceed 14
days. Nothing is at a capacity ceiling. Improving the ranker is *not* blocked by
plumbing.

**"It is what they are holding."** No. Total unrealised is **−$905** across 20
positions.

**"It is transaction costs."** No, and this one I got wrong first. Seeing "98%
realised" I inferred §59's toll was being paid repeatedly — because that was the
explanation I already had. The arithmetic refutes it:

    realised loss        -$46,401
    traded notional    $2,090,090
    per dollar traded       222 bps
    §59's round-trip toll  6-35 bps

Friction explains at most a sixth. **The entries are directionally wrong.**

## 2. The real mechanism, and the number that matters

358 closed round trips, FIFO-matched from 500 fills:

| | |
|---|---:|
| hit rate | **27.7%** (97 of 350) |
| per position taken | **−418 bps** |
| mean winner | **+1.91%** |
| mean loser | **−7.00%** |
| median hold | **1 day** |
| winners held | 1.1 days |
| losers held | **3.5 days** |

EV per trade = 0.277 × (+1.91%) + 0.723 × (−7.00%) = **−4.53%**, which matches
the −418 bps measured.

At a 28% hit rate, break-even needs winners **2.6×** the size of losers. Instead
losers are **3.7×** winners — the payoff ratio is inverted by roughly nine times.
**The books cut winners at +1.9% and let losers run to −7.0%, holding the losers
three times longer.**

### What a stop would have been worth

| stop | realised P&L | saved |
|---|---:|---:|
| actual | −$39,436 | — |
| **−2%** | **−$10,010** | **+$29,426 (75%)** |
| −3% | −$16,666 | +$22,770 (58%) |
| −5% | −$22,023 | +$17,413 (44%) |

**Stated honestly:** this counterfactual assumes capping a loss is free and it
is not. Stops get whipsawed, some of those −7% losers would have recovered, and
a gap can fill below the level. Treat 75% as the optimistic end of a range whose
pessimistic end is still large.

**And the caveat that matters more:** even with perfect exits, a 28% hit rate
with these magnitudes only reaches ≈ −$4k. **Fixing exits stops the bleeding; it
does not make money.** The selector is negative and the exit rule amplifies it.

### Entry characteristics: nothing survives

Winners vs losers at entry, across ten features: only `amihud` (t +2.11,
winners more illiquid) and `px_vs_52w_high` (t −2.10, winners further below
their high) reach |t| > 2, on 350 trips with ten features tested. Neither
survives multiplicity. **There is no screenable property of the names that
separates them** — which points at timing and sizing rather than at selection
alone.

> A methodological note against myself: the first run of this comparison
> reported `ret` at **t +25** as the top discriminator. `ret > 0` is the
> DEFINITION of a winner. I had let outcome columns into a comparison that was
> supposed to be about what was knowable at entry — the same leakage rule this
> repo enforces everywhere else, broken in the one place it was being used to
> draw a conclusion.

## 3. Does holding longer rescue §59? No.

§59 closed price/volume with "edge 28 bps, toll 35 bps". But the toll is paid
per ROUND TRIP, not per day — so a longer hold pays the same toll over more
time. If the signal is slow-moving, some horizon should turn it profitable with
no new data.

Swept 21 / 42 / 63 / 126 sessions, everything else held fixed, **purge scaled
with the horizon** so the long cells are not leaking:

| horizon | net/yr k=20 | net/yr k=200 | IC (t) |
|---|---:|---:|---:|
| 21 | −13.05% | −5.48% | +0.0162 (+5.30) |
| 42 | −9.55% | −5.52% | — |
| 63 | −5.03% | −4.24% | +0.0074 (+2.76) |
| **126** | **−2.84%** | **−1.99%** | **+0.0247 (+10.45)** |

Holding longer helps enormously — −13% to −2% per year — and never crosses zero.
And the reason is not cost: **gross is negative at every horizon**, so there was
no toll to save.

**The limitation, stated:** this swept LightGBM-on-all-features, which §59 had
already shown was the *worst* of four models (gross −0.30%). The model that was
gross-**positive** (`composite_prior`, +0.28% at every k) was never swept. So
the verdict "horizon does not rescue it" is established for the wrong model.
Sweeping `composite_prior` across horizons is the obvious next run and it is
owed before this is treated as closed.

Once more, the recurring lesson: **H=126 has the highest IC of all four
(t +10.45) and the losing book.** Promote on the economic objective at the k you
hold, never on IC.

## 4. What this changes

**For the Railway fleet** — the finding is not "pick better". It is that a
selector with a 28% hit rate is being amplified by an exit rule that cuts
winners early and holds losers. A stop is worth ~$29k of the last $39k on the
evidence available. **That is a proposal for a human, not an action from here:**
these accounts are owned by the Railway loops, and a second writer is exactly
what `pc_broker`'s execution lease exists to prevent.

**For the PC book** — its refusal to trade a measured-negative ranking now has a
live counterfactual. The fleet is what happens when a negative selector is
traded anyway: −418 bps per position, 358 times.

**For the research queue** — three of tonight's four hypotheses were refuted at
$0.00, which is the point of running them. The one survivor (exit discipline) is
an operational fix, not alpha. The alpha question is unchanged and still waits
on the SEC fundamentals join.

## 5. Receipts

| file | what |
|---|---|
| `fleet_audit/fleet_audit_2026-09-24.json` | per-book equity, gross, staleness, capacity |
| `fleet_audit/trade_autopsy_2026-09-24.json` | 358 round trips, entry features, discriminators |
| `xs_ranker/horizon_sweep_2026-09-24.json` | 4 horizons × 4 book sizes, purge scaled |
| `sim/0b2c8110ef68/` | the 10-hour session running alongside |
