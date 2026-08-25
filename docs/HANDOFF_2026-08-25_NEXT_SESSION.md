# HANDOFF 2026-08-25 — the night the sample got three times bigger and said no anyway

## RESULTS SCOREBOARD

| | |
|---|---|
| best historical net strategy vs market | `mom_12_1 / h=5 / k=20 / inverse_vol / u500 / 12bp` — **4.41x** the market over 1993-2024 ($971k from $10k), `t`=1.99, **61 years needed to demonstrate** |
| best forward paper strategy | **none seeded.** Unchanged for the fifth month |
| independent selector count | **1.** `profit_roe` is a candidate, not a selector |
| farm candidates tested / promoted | 18 signals x 7 breadths x 4 windows x 5 phases / **0** |
| new actionable finding | **Nothing in the farm beats a book of the hundred oldest listings, resolvably.** `profit_roe` needs 126 years to clear it, `mom_12_1` needs 72 |
| external execution drag | n/a — nothing seeded, `execution_ledger` correctly absent |
| LLM spend | **$0 this session.** The farm is numerical; the DeepSeek balance was not touched |

**RESULT IMPROVEMENT: MEASUREMENT YES, EDGE NO.** The demonstrated edge is
still 0%. What moved is the quality of the question: the farm can now ask
"better than what?" and get an answer, and the answer for both candidates is
"not demonstrably better than holding old companies."

## What was done

### 1. The CRSP re-pull, authorised and complete
`scripts/wrds_repull_dsf_early.py`. **Replayable window is now 1993-2024 (32
years)**, up from 12. The resume key is COLUMNS rather than file existence —
`wrds_pull_catchup` skips any table whose parquet exists and therefore can
never see a partially-pulled one.

1990-92 are permanently unusable and neither reason is fixable: CRSP has no
open prices before mid-1992 (`openprc` 0.0% in 1990-91, 46% in 1992), and the
early PIT universe carries 243-475 eligible names against a top-500 cut, so
there the cut IS the screen. `replayable_years` gates on **coverage**, not on
the column being present — a column is not data, and the gate would otherwise
have certified an empty 1990.

### 2. The split-adjustment bug — the fifth "instrument beat strategy"
The panel marked **share counts at raw prices**, so every split was booked as a
return. One reverse split was +36.34% of a single day's excess and the top
session of twelve years for both momentum signals.

Found by printing the **dates** of the top sessions, not the distribution:
2015-01-02 topped both momentum signals at +36.34% and +35.53%. An identical
extreme on one date for two different rules is an instrument, not an effect.

Net cost was ~0.3%/yr. The distributional cost was the entire signal ranking —
forward splits are commonest among large liquid names. Fixing it moved `liquid`
from t=0.26 to t=2.55, which is how it came to look like the best thing on the
board for about four hours.

### 3. A second data source — the first signals that are not price
`backend/services/portfolio_farm/characteristics.py` joins WRDS `finratio` PIT
and registers `value_bm` and `profit_roe`.

**All thirteen previous non-null signals were thirteen views of one file** —
past returns, market cap and dollar volume are all columns of `crsp.dsf`. A
library like that cannot produce an independent selector however many entries
it gains, because independence is a property of the DATA, not the formula.

`public_date` is the availability stamp and a value may be used STRICTLY after
it. `searchsorted(side="right")` there is a lookahead that improves every
number and raises nothing.

### 4. The 32-year verdict on the incumbent

| | 2013-2024 | 1993-2024 |
|---|---|---|
| tracking error | 35.7% | 34.4% |
| observed excess | 16.64% | **12.36%** |
| implied `t` | 1.54 | 2.00 |
| MDE at 80% power | 30.3% | 17.3% |
| **years needed** | 36 | **60.7** |

`sqrt(T)` halved the standard error exactly as advertised **and the effect
estimate shrank at the same time**, so the target moved further away. By decade
the candidate reads 4.38x / **0.43x** / 2.09x — over 2003-2012 it turned
$10,000 into **$6,813** while the market made 58%.

**A "years needed" figure computed from a window that omits a regime is a lower
bound dressed as a target.** Whenever it is quoted, quote the excess it came
from and name the regimes the window omits.

### 5. Breadth — the 12-year verdict reversed
The queued question was whether the excess falls faster than tracking error as
`k` rises. On 12 years it did (`mom_12_1` slope -0.40, peak at the narrowest
book). **On 32 years it reverses**: slope +0.02, peak `t` at k=20, which is
also the best book by terminal wealth ($971k vs $614k at k=10).

The 2013-2024 read was itself a regime — that window was a mega-cap decade in
which concentration paid.

Breadth also **separates a signal from a description of a decade**, cheaply:
`liquid` runs slope -1.11, its excess is gone by k=20 and negative by k=30. Its
entire edge is ten names (MSFT 123/124 samples, GOOG 87, AAPL 81). The holdings
census said that in tickers; the breadth curve says it in a number, so it is
now the **first** screen on a farm candidate rather than the last.

### 6. `profit_roe`, and the benchmark that took it apart
At k=100 it returned +2.56%/yr over the market against an MDE of 2.57% — it
needed **31.2 years and the window is 30.88**. Nothing in this project had ever
come within four months of its own detection threshold.

The null-breadth run was fired to kill it and did not: every null DECAYS with
breadth (`random` -1.45, `random_persistent` -0.80, `equal` -0.38) while
`profit_roe` is the only signal on the grid whose `t` rises (+0.69). The
construction produces the opposite shape.

**Then the right benchmark killed it anyway.** `equal` is not equal-weighting —
with every score tied, `top_k` falls through to permno order, so it is *the
hundred oldest surviving listings*. High-ROE large caps ARE old listings: CL,
CLX, AVP, LMT, UST, MHP.

    1993-2024, same construction, phase matched pairwise, median phase
    comparison                          te%   excess%     t   mde80%  yrs  resolves
    profit_roe vs equal        k=100   6.11     +1.53  1.39     3.08  126  0/5
    profit_roe vs random_pers. k=100   5.33     +2.22  2.32     2.68   45  0/5
    mom_12_1   vs equal        k= 20  27.92     +9.23  1.84    14.07   72  0/5

Both signs are stable across all five rebalance phases, so neither is a
calendar artefact. Neither is evidence.

**`scripts/portfolio_farm_paired_power.py` is the new instrument** and it is the
lasting piece of this session: every power check in the farm compared to the
cap-weighted market, which asks "should I hold this instead of an index" — the
right question for a product and the wrong one for a claim about a signal,
because two books can beat the market for the same reason and neither of them
be the reason.

### 7. Four defects, each found by doing the work rather than auditing

1. **The breadth receipt clobbered itself.** Keyed on the window alone, so
   `--signals a b` deleted what `--signals c d` had written. Two batteries ran
   overnight and only the second survived in the receipt. Now merges on
   `(signal, top_k)` and refuses to merge across a different construction.
2. **The breadth verdict called two loss-making signals "SCALES with breadth".**
   `value_bm` (`t` -0.77 → -0.39) and `low_vol` (-1.09 → -0.84) both have
   positive slopes while losing at every breadth. A rising `t` on a negative
   excess is a loss diluting. Exactly two signals score as scaling now.
3. **The paired script asserted pairing is the EASIER test** — in its docstring
   and its conclusion line. Its own first three runs refuted it (te 5.10% vs
   market, 6.11% vs the age book). Now measured and printed, not assumed.
4. **`monday_gate_check` reported a FAIL no state of the system could clear.**
   See below — this is the one to read.

## THE ONE TO READ: a red line that could not go green

`monday_gate_check` has printed **"seed migration → book-v1: 0/9 stamped
[FAIL]"** for weeks. `engine.status()` never emitted `fingerprint_scheme`. The
gate reads it off that payload, so the count could only ever be 0/N.

Verified against production 2026-08-25 — the keys served per book were
`last_nav, nav_rows, positions, seeded, seeded_at, validation_status`, and
nothing else.

**The seeds were never failing. Their state was invisible, and a check with no
input reported the absence as a failure.**

Both sides fixed, and the second matters more: `status()` now serves
`fingerprint_scheme`, `book_fingerprint` and `composite_version`; the gate
reports **CANNOT DETERMINE** when no book carries the key, per the standing rule
that *guards derive their inputs or refuse*.

A red line that cannot go green is worse than a missing check, because it
teaches the reader to skim red lines — and there were nine real checks beside it.

## THE OTHER ONE TO READ: options_pit was never on the volume

Found by watching the gate across my own deploy, which is the only reason it
was visible at all:

    10:27 local   options_pit accruing: ok rows=179 days=1
    10:59 local   options_pit accruing: ABSENT rows=0 days=0

`options_pit_store._root()` read `os.environ["OPTIMUS_LEDGER_DIR"]` — a
variable nothing sets — and fell through to
`Path(__file__).parents[1]/"data"/"optimus"`, **a path inside the container
image**. Railway sets `AEGIS_DATA_DIR=/data` and mounts the volume there;
`config.OPTIMUS_LEDGER_DIR` honours that, and **every other ledger-writing
service in the codebase imports that constant.** This module was the only one
reading an env var.

**`days_held` has never once exceeded 1.** That is the same fact seen from the
other side: the store could not accumulate, because every deploy reset it.
`monday_gate_check` states the cost in its own words — *"option chains have NO
history; a missed day is gone."* Every day it ever collected is gone. That is
not recoverable; what is fixed is that it stops.

It also hid from the suite: the rest of the tests override storage by
monkeypatching `config.OPTIMUS_LEDGER_DIR`, which this module never consulted,
so its tests exercised a resolution path production never used.

**The control that makes the diagnosis certain:** arena seeds and `event_store`
persisted across the very same deploy. They resolve through config; they
survived. options_pit did not.

Guard added — `backend/tests/test_ledger_dir_resolution.py` refuses any service
that rebuilds a ledger path from `__file__` or reads the env var without a
config fallback. Verified it bites: reverting `_root()` fails 4 of its 9 tests.

**Not yet verified in production:** the fix is deployed, but `pi_options_pit`
fires at 15:30 ET, so the first accrual onto the volume lands then. **Check
`options_pit accruing` on the next session and confirm `days_held` climbs past
1 — that number has never been above 1 in this system's history.**

## What is left

### Unblocked and ordered

1. **The IBES revision signal.** `ibes_consensus_monthly*` is on disk for both
   eras with `numup`/`numdown`. It is one join away in `characteristics.py`,
   and it is the third non-price signal — the only cheap route to the
   independent-selector count that is the stated bottleneck.
2. **Neutralise `profit_roe` against listing age.** Rank ROE *within* age or
   size buckets so the signal is not partly a proxy for "old company". This
   removes the confound and could sharpen the signal at the same time; the
   paired test above is exactly the instrument to score it.
3. **Run `paired_power` against `equal` for every candidate, as standard.** The
   age book is the hardest benchmark the farm has used and it is nearly free.
   Any signal that cannot clear it is not about its own quantity.
4. **Re-run the breadth grid at k=20 for the holding-period preset.** k=20 is
   now the best `mom_12_1` book on both terminal wealth and `t`, and every
   holding-period result on record was computed at k=10.

### Blocked

- **DeepSeek top-up** — Murat said he would do it. $0 was spent this session.
- **Remote Control re-authentication.**
- Anything needing transcripts (items B/D) and anything needing three selectors
  (item G) remain blocked as of the 2026-08-24 handoff.

### Verify on next session

- `python -m scripts.monday_gate_check` — the seed-migration line should now
  read either a real count or CANNOT DETERMINE, never a bare 0/9 FAIL.
- **DONE and verified live:** `/api/arena/status` serves `fingerprint_scheme`
  for 9/9 books, and all nine read `book-v1`. The migration had completed long
  ago — the gate was reading a field that was never served. The gate line now
  reads `9/9 stamped [ok]`.
- **`options_pit accruing` — the one to actually check.** `days_held` must climb
  past 1 after the next 15:30 ET firing. It never has.
- `nav.all_fresh` was **false** at handoff: all ten lanes sit at 2026-08-21
  against an expected 2026-08-24. `pi_daily_check` last fired 16:30 ET Monday,
  six hours BEFORE my deploy, so this predates the session's changes. Not
  diagnosed — it is the first thing to look at.

## What this session says about the method

**Three verdicts flipped when the instrument changed, not when the strategy
did** — the split fix reordered the signal ranking, the 32-year window reversed
the breadth conclusion, and the age benchmark reversed the `profit_roe`
near-miss. That is now five instances on record.

The corollary is getting sharper each time: **distrust a farm number before you
distrust a farm result, and ask "better than what?" before "how much better?"**
Every power check in this project compared to the cap-weighted market for five
months. The first time a harder benchmark was tried, both candidates failed it.
