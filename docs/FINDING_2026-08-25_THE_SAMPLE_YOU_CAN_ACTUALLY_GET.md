# FINDING 2026-08-25 — the sample you can actually get is 32 years, not 35

## RESULTS SCOREBOARD

| | |
|---|---|
| best historical net strategy vs the market | `mom_12_1 / h5 / k=10 / inverse_vol`, $77,002 median vs $38,960 (2013-2024) — **unchanged, still not seedable** |
| best forward paper strategy | none launched |
| independent selector count | **1** (12-1 momentum), unchanged |
| farm candidates tested / promoted | ~1,700 / 0 |
| new actionable finding | the replayable window widens 12 → **32 years**, and two independent constraints both stop at 1993 |
| external execution drag | not measured this session |
| LLM spend / cost per gradeable output | $0 this session (no LLM calls made) |

**RESULT IMPROVEMENT: NONE.** No strategy improved, no book launched, the
demonstrated edge is still 0%. What changed is the size of the sample the next
run gets to use, and one guard that would otherwise have produced a fake result
from it.

---

## 1. What the re-pull actually bought

The 2026-08-24 power check said 12 years could never resolve the effect it was
measuring:

```
tracking error  35.7%/yr    implied t          1.54
observed excess 16.6%/yr    MDE at 80% power  30.3%/yr
years available   10.9      YEARS NEEDED        36
```

and named the fix: CRSP 1990-2024 is 35 years, near enough to 36. That framing
was too optimistic by three years, for two reasons that had to be measured
rather than assumed.

**CRSP has no open prices before mid-1992.** Measured at the source:

| year | `openprc` coverage |
|---|---|
| 1990 | 0.0% |
| 1991 | 0.0% |
| 1992 | 41.6% (46.0% inside the pulled universe) |
| 1993 | 82.6% |
| 2013 | 93.2% |
| 2024 | 99.4% |

Without an open there is no next-open fill, and the only executable fallback is
close-to-close — which books the overnight gap that *follows* the signal, a
systematic gift to exactly the strategies being searched for.

**The early universe is too thin to screen before late 1992.** The early PIT
file applies the same NOMINAL cuts as the modern one ($5, $100M/month), and a
nominal bar in 1990 is a much stricter real bar:

```
eligible names per month   min 243   median 1,332   max 2,149
months with < 500 eligible    32 of 276, ALL of them 1990-01 .. 1992-10
```

The farm's universe is the top 500 by trailing dollar volume. In those 32
months the cut IS the screen boundary rather than a selection from a wider set,
which is the exact condition `portfolio_farm_universe_audit` refuses to clear.

Both constraints end at the same year. **The replayable window is 1993-2024:
32 years**, against the 36 the effect needs. `t` scales with `sqrt(T)`, so
1.54 → ~2.6 *if the effect is stable* — and whether it is stable is the actual
question. 1993-2024 contains the dot-com peak, the GFC and COVID. 2013-2024
contains none of them.

**The honest prior is that the excess shrinks.** 2013-2018 already returned
1.01x the market on the leading rule where 2019-2024 returned 1.75x. A smaller
excess with an interval that excludes zero would be the better outcome. The
point was never the number.

## 2. The guard the re-pull made necessary

`replayable_years` certified a year on the PRESENCE of `openprc`/`retx`/
`shrout`. That was correct against the failure it was written for — the
1990-2012 pull requested five columns and those years had to be refused by
name. Giving them the full schema would have flipped every one to REPLAYABLE
while the column was empty.

A 1990 replay would have filled nothing (`replay` refuses a non-positive open)
and produced a **buy-and-never-trade book wearing a momentum policy's hash** —
the strongest form of the failure that has already moved a farm answer more
than a strategy did, four times.

So the gate is now on COVERAGE, and an empty column gets its own refusal
because its fix is different: there is nothing to re-pull. The floor is 60%,
sitting inside the empty gap CRSP itself leaves between 41.6% and 82.6%, so its
placement cannot change a verdict.

**A column is not data.** That is the generalisable form, and it is the sibling
of two failures already in the ledger — *"a failure-driven queue cannot see a
NEVER-ATTEMPTED item"* (2026-08-23) and *"an existence-keyed queue cannot see a
PARTIALLY-PULLED item"* (the re-pull script's own reason for existing).

### A worry this settled on the way past

`Panel.open_coverage` now reports the signed truth on the loaded window, and
the first thing it said was reassuring: **inside the top-500 liquid universe
the farm actually trades, `openprc` coverage is 100.00% in every year
2013-2024.** The ~2.2% missing rate quoted in `replay`'s comments is over all
CRSP rows, which is dominated by illiquid microcaps the farm never holds.

So the 2013-2018 vs 2019-2024 disagreement is **not** a fill artefact. It was
worth checking: coverage rises from 93.2% to 99.4% across that window in the
raw file, which would have been a mechanical explanation for a strategy that
executes better late than early.

## 3. A 32-year panel does not fit, and halving it changes nothing

The two PIT universe files union to 18,691 permnos across 8,064 sessions —
0.6 GB per float32 matrix, ~4.8 GB for the eight a `Panel` carries, before the
pandas frame that builds them.

Nearly all of it is arithmetic on NaN: over 2013-2024 only **1,967 of 6,894
permnos (28.5%) ever reach the top 500** by trailing dollar volume.

`liquid_permnos` keeps the names that could enter a book, using the criterion
`replay` itself uses, and halves the panel. Verified rather than argued:

```
ALL EIGHT NAV SERIES IDENTICAL to 1e-6
  4 signals x 3 holding periods x 2 sizings x 5 rebalance phases, 2013-2024
  full 6,894 permnos vs reduced 3,481
```

The reduction is **not** point-in-time — it reads the whole window to decide
which columns to materialise, exactly as the PIT superset's construction does.
That is sound for a MEMBERSHIP question and would be fatal for a signal, so the
boundary is enforced rather than documented: a policy asking for a deeper
universe, or a different price floor, is REFUSED.

## 4. What this does and does not license

Under the three licences this is all `PRODUCT_EXPERIMENT` plumbing. It licenses
running the farm on 1993-2024. It licenses nothing about momentum, and it moves
no candidate toward `CAPITAL_CANDIDATE`.

The 32-year run is the thing that will say something, and the question it
answers is not "is the number bigger" — it is **"could this sample have carried
the number at all, and does the rule survive three regimes it has never seen?"**

## 5. Standing items this does not touch

- **EVENT-RESPONSE-2 is `NOT_LICENSED_BORROW_CONFOUNDED`.** Excluding the top
  borrow quintile (20% of events) removes >50% of the drift IC at 1d and 61% at
  5d, and the point estimate halves rather than the error widening — so it is
  not a power artefact. The board therefore has **no unblocked alpha item**,
  which is why the data was the right thing to spend the night on.
- **There is no premarket news job to move.** The two morning jobs are
  `pi_ownership_collect` (06:00 ET, structurally one day behind because EDGAR
  publishes a day's index after that day closes) and `pi_congress_collect`
  (07:30 ET, timed for a fresh FMP quota). Neither is news, and the decision
  loop is a post-close one — it decides at 16:30-17:45 ET and fills at the next
  open, so pre-market news on the fill day is *by construction* not usable.
  That is correct PIT discipline, not a lost opportunity.
