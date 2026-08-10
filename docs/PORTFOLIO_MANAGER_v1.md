# Optimus Portfolio Manager v1 — the product, and what it is honestly worth

**Built:** 2026-08-10 (NIGHT-9) · **Reference account:** `murat_live`, $45,000
**Run it:** `python scripts/morning_brief.py` · **API:** `GET /api/pm/daily`

This is the answer to a direct instruction: *"it matters more to me that I can
manage the $45k I have with this engine."* Aegis had been behaving like a
research laboratory. That work is what keeps us from fooling ourselves, and it
continues — but it is not the thing you use in the morning.

---

## What it does

One command prints the whole morning:

```
PORTFOLIO $45,000   cash $0
12-MONTH VIEW    median $64,501   p25 $46,032   p75 $90,992
                 P(reach target) 19.8%   P(below floor) 5.9%   P(below ruin) 0.8%
                 expected max drawdown -27.1%   P(worse than -50%) 5.3%
                 required return for the target +122.2%

HOLDINGS    PRICE      P&L   WEIGHT   TARGET   UPSIDE   SCORE  ACTION
MSTR      $100.01   -60.0%    11.1%    15.0%   +93.0%   0.754  ADD  $1,750
SOC         $4.75    -5.0%     8.9%    11.8%  +194.7%   0.641  ADD  $1,314
...
AARD        $7.90   -21.0%    12.2%     5.1%   -17.7%   0.000  TRIM $-3,218
```

then the tickets with their kill conditions, the threats, the opportunity radar
over the watchlist, and which holding would fund which new buy.

Every number above is live. Nothing in it is a mock-up.

## The five things it does that a screener does not

1. **It prices the analyst target instead of believing it.** Every implied
   upside is multiplied by a **haircut of 0.35** before it reaches a
   probability, and a further 0.60 knocked off for pre-revenue clinical names
   whose "consensus target" is a probability-weighted hope quoted as a price.
   The haircut is printed next to every result because it is the single most
   consequential number in the system **and it is an assumption, not a
   measurement**. Replacing it with a measurement is the first thing the journal
   below is for.

2. **It ranks revisions, not just levels.** A stock at $20 with a target that
   went $60 → $52 → $46 → $40 is not the same as one whose target went $21 → $23
   → $26 → $30, and the naive `target/price − 1` screener prefers the first. The
   score multiplies upside by rating drift over three months, by net
   upgrades-minus-downgrades over ninety days, and by a freshness decay on the
   last rating action — so stale coverage and a fading street both cut it.

3. **It asks the portfolio-manager question, not the stock-picker question.**
   Never "is DKNG good"; always "is this candidate a better use of the dollar
   than the weakest thing I already own, after a 40bp round trip". The brief
   names which holding funds which purchase.

4. **It reports the downside in the same breath as the target.** The wealth
   simulation is a twelve-step monthly path — not a terminal shock with a fudge
   factor — so the drawdown is a real peak-to-trough. `P(reach $100k)` is
   **never** printed without `P(below $30k)`, `P(below $20k)` and the expected
   maximum drawdown beside it. A stretch target quoted alone reads as a
   forecast, and it is not one.

5. **It writes down why.** `/api/pm/journal/record` freezes every instruction
   with the state that produced it — price, target, dispersion, analyst count,
   rating drift, thesis, kill condition. Append-only; a resolution is a new row,
   never an edit. In three months that is what lets you ask *which part* was
   wrong: the stock, the catalyst, the analyst, or the size.

## Sizing modes change risk, never evidence

| mode | max per name | max names | Kelly fraction | min cash |
|---|---|---|---|---|
| `growth` | 10% | 20 | 0.25 | 5% |
| `high_growth` | 15% | 15 | 0.40 | 2% |
| `moonshot` | 25% | 12 | 0.60 | 0% |

`python scripts/morning_brief.py --mode moonshot`. The evidence, the haircut and
the distribution are identical across all three. Only the position limits move.
That separation is deliberate: a mode that also loosened the evidence would be a
machine for telling you what you want to hear.

## The maths, stated plainly so it can be attacked

* **Distribution.** One lognormal per name. Its *median* twelve-month return is
  `haircut × analyst implied upside`; its volatility is the name's own trailing
  annual volatility. Bear and bull are that distribution's 10th and 90th
  percentiles, clamped — never widened — by the street's own low and high.
  An earlier version mixed a haircut median with a raw two-sigma bear leg; the
  expected return came out negative for almost every name and the engine
  recommended selling seven of eleven positions. That was an artifact of mixing
  two incompatible objects, not a view about the stocks, and it is why the
  distribution is now built exactly one way and read exactly one way.
* **Sizing.** Fractional Kelly, `f × μ/σ²`, **uncapped at first**, then scaled
  into the mode's budget, then capped, with the overflow redistributed. Capping
  before scaling made every name in a high-conviction book hit the same ceiling
  and come out equal-weight, throwing away the ordering the score had just
  computed.
* **Portfolio simulation.** 20,000 paths, twelve monthly steps, one common
  factor at an assumed average pairwise correlation of **0.35** plus
  idiosyncratic noise. Small-cap high-beta books cluster hard in drawdowns and a
  zero-correlation simulation would flatter this one badly.

## What it is NOT, and where it can hurt you

* **The analyst layer is observational and unvalidated.** The Aegis research lab
  has not tested whether consensus-target upside predicts returns on our own
  data. Until it has, this is a *disciplined version of a process that has been
  run by hand* — not a demonstrated edge. Every payload says so in a field named
  `evidence_grade`.
* **The haircut is a guess.** 0.35 is in the right region for how far consensus
  targets overshoot, but it is not fitted to anything we own. If the true figure
  is 0.15, the engine is systematically over-sizing; if 0.60, under-sizing.
* **Correlation is a single number.** Real correlation rises exactly when it
  hurts. The 0.35 assumption understates a crisis.
* **Catalysts are not in v1.** Earnings dates, FDA calendars, lockups and
  readouts are the obvious next layer, and for a book this concentrated in
  clinical names they matter more than anything the score currently sees.
* **The shipped book is UNCONFIRMED.** Positions were reconstructed from the
  January 2026 research PDF, which lists tickers and prices but no share counts
  and no cash. Every dollar figure carries a banner until
  `backend/data/murat_book.yaml` is corrected and `confirmed: true` is set. The
  engine will still record its reasoning to the journal, marked as reasoning
  rather than as executed trades.

## What the engine currently says about the $45k book

Under the base assumptions, with the reconstructed positions:

* the median twelve-month outcome is **~$64,500**, the interquartile range
  **$46,000 – $91,000**;
* the probability of reaching **$100,000** is **~20%** — the target needs
  **+122%** and it is a one-in-five outcome, not a plan;
* the probability of ending below **$30,000** is **~6%**, below **$20,000**
  ~1%;
* the expected maximum drawdown along the way is **−27%**, and about one path in
  twenty goes through a drawdown worse than **−50%**.

Two structural observations the engine surfaces without being asked. The book is
**eleven names, several of them binary clinical stories, and it is
concentrated**: three of the largest weights carry single-event risk. And
**AARD trades above its consensus target** with two net downgrades in ninety
days and under $1m of median daily volume — it scores zero and is the largest
trim in the brief.

## Where this goes next, in order

1. **Confirm the book.** Share counts and cash. Everything downstream is a
   placeholder until then.
2. **Catalyst calendar.** Earnings, FDA/PDUFA, readouts, lockups, offerings —
   event-driven recomputation rather than a daily sweep.
3. **Analyst reliability, per analyst and per firm.** Not "JPMorgan says Buy"
   but "this analyst's small-cap biotech targets have been 25% too high for
   three years". That is where the haircut stops being a guess.
4. **Score the journal.** Once fifty instructions have resolved, fit the haircut
   to them and retire the assumption.
5. **Widen the radar** beyond a 34-name watchlist to a real universe sweep.
