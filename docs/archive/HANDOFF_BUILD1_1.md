# HANDOFF → after BUILD-1.1

Written 2026-08-10. BUILD-1.1 was a **product-correctness** build, not a
research night and not a feature night. External review of PM v1 found six
defects that made its dollar figures untrustworthy. All six are fixed; **eight
more were found on the way** — four while fixing them and four from the
project's own silent-fragility audit — and the analyst spine that B1 required
now exists.

Read `docs/PORTFOLIO_MANAGER_v1_1.md` for the full design rationale. This is the
operational handoff.

---

## Commits

| repo | commit | state |
|---|---|---|
| aegis-finance | `d54723f` (parent `0c3f170`) | clean |
| Aegis module | `be0c786` (on `dccea33`) — research untouched by this build | clean |

No lane seeded, no flag flipped, no `paper_nav` written, no keys changed.
**LLM spend: $0.** NIGHT-9's findings, G8, the N2 corrigendum and the rank-IC
standing wording are all preserved and unmodified.

---

## Every bug found, and what it was doing

### The six from review

1. **The book did not mark to market.** `daily_brief` valued positions from
   `Position.dollars`, a static YAML number; `shares` was in the schema and read
   by nothing. A book could report "$45,000" indefinitely while its holdings
   halved, and every weight, ticket and probability downstream was consistent
   and wrong. → `shares × live price` is authoritative; a confirmed book without
   share counts is rejected at load.

2. **A missing feed could become a SELL.** One `available` flag meant "we got a
   price". Price + no target → no distribution → weight 0 → SELL. → four
   separate states (`market_data_status`, `analyst_data_status`,
   `distribution_status`, `decisionable`); a held name that is not decisionable
   is REVIEW, a candidate that is not decisionable is SKIP.

3. **Volatility manufactured expected return.** The lognormal's *median* was set
   to `haircut × upside` and its *mean* was reported — larger by `exp(σ²/2)`.
   A 90%-vol name earned ~40% more expected return than a 30%-vol name off the
   same target, then a larger Kelly weight for it. → the target after haircut
   and reliability **is** the mean; σ widens and cannot move it.

4. **The replacement edge mixed units** — a 40bp return subtracted from a
   difference of two arbitrary scores, then labelled "net of a 40bp round trip".
   → certainty equivalents in expected-return units, cost in the same units.

5. **Two lists pretending to be a portfolio.** Holdings sized, watchlist ranked
   separately, switches labelled afterwards; the wealth simulation never saw the
   candidates. `max_names` was defined and never read. → one solved portfolio
   over holdings ∪ candidates, with the replacement table as its decomposition.

6. **A three-significant-figure probability off an unfitted assumption.** →
   conservative / base / optimistic printed together, every arm with its
   downside.

### Four found while fixing those

7. **A junk quote was charged as a real cost.** Live: Yahoo returned AARD at
   bid 5.48 / ask 9.60 **in a size of two shares** while it last traded at 7.50.
   Doubled into a 55% round trip, which made every replacement comparison
   touching the name meaningless — observed switch costs of 0.60–0.83 in the
   live brief before the fix. → a quote must bracket the last trade within 1%,
   be under 500bps, and show a round lot; otherwise `spread: unavailable`.
   Round-trip cost capped at 5%.

8. **The intraday range sat where it could be read as a spread.** → renamed
   `intraday_range_pct`, carries `"a RANGE, not a quoted spread, and not a
   cost"`.

9. **The optimiser churned, because it does not charge trading costs.** → the
   no-trade band scales with the name's round-trip cost. The pair-level check
   survives as labelled DISSENT and is counted in `model_status`.

10. **Suppressed trims could fund purchases with no cash behind them.** The band
    kills a $200 funding trim as happily as a $200 top-up. → `enforce_cash_constraint`
    scales buys to what the sales actually raise, and reports the reconciliation.

### Four more from the silent-fragility audit

The project's own discipline (`.claude/skills/silent-fragility-audit`) was run
over the diff, because it adds collectors, fetchers and `try/except` blocks —
its exact trigger. It found four instances of the house failure mode, three of
which would have run green forever:

11. **A guessed volatility was silent and permanent.** `_vol` swallowed every
    exception, substituted `FALLBACK_VOL = 0.65`, and **cached it for the life
    of the process**. Every Kelly weight is `μ/σ²`, so one transient Yahoo
    failure quietly quartered a low-vol name's position and nothing said so.
    → the fallback is logged at WARNING, recorded in `VOL_FALLBACKS`, surfaced
    in `model_status.volatility_fallbacks` and on the CLI as
    `! GUESSED VOLATILITY`, and **not cached**, so recovery is possible.

12. **A failed binary-event check biased toward risk.** `_looks_binary`
    returned `False` on any exception, which *removes* the 0.60 extra haircut
    and therefore makes the position **larger** — in precisely the pre-revenue
    clinical names where the risk is binary. → the skipped check is recorded
    and printed as `! BINARY CHECK SKIPPED — treated as non-binary, the LESS
    conservative assumption`.

13. **A 403 calendar was indistinguishable from a quiet quarter.** The catalyst
    layer exists so that silence never reads as safety, and its own fetch
    failure produced an empty list exactly like a genuinely empty window. →
    `CatalystFetchError`; failures are never cached as empty; `coverage()`
    reports `tickers_not_retrieved` and grades itself `v0 DEGRADED — N tickers
    were NOT retrieved; their calendars are UNKNOWN, not empty`.

14. **A corrupt ledger row vanished into a healthy-looking smaller ledger.**
    → counted in `MALFORMED_ROWS`, reported by `coverage()`, printed as
    `! LEDGER CORRUPTION`.

Checks run: swallowed exceptions, runs-but-fetches-nothing, status surface,
rate limits and volume, hangs/timeouts, degraded-≠-fabricated, cache masking,
contract drift at load boundaries. **Not covered:** no `/api/health/full`
canary was added for the PM — it is user-invoked rather than scheduled, so
`model_status` is its health surface, and a scheduled PM job would need one.
yfinance calls still carry no explicit timeout (pre-existing repo-wide pattern,
BACKLOG).

### One finding, not a bug

For this book the **conservative scenario prints a higher P(reach $100k) than
the base scenario** while ending poorer in the median and ruined more often.
$45k → $100k in twelve months needs +122%: that is a variance outcome, not a
drift outcome. The brief sets `volatility_dominates_target` and says so, because
a reader seeing only "conservative: 4.6%" would take exactly the wrong comfort.

---

## What the fixes did to the headline numbers

| | PM v1 | BUILD-1.1 | why |
|---|---|---|---|
| median 12m (reconstructed book) | $64,501 | ~$48,500 | P0.3 — the mean was the median times `exp(σ²/2)` |
| P(reach $100k) | 19.8% | ~1.7% base, 1.7–3.2% across scenarios | same |
| P(below $30k) | 5.9% | ~5.6% base, up to 16.9% conservative | same |
| expected max drawdown | −27.1% | −22.4% base, −31.3% conservative | same |
| switch costs | 0.4% flat, wrong units | 0.4–0.8% observed/assumed, capped at 5% | P0.4 + bug 7 |

**The old numbers were the convexity of an unvalidated assumption.** The new
ones rest on the same unvalidated assumption but no longer add a volatility
bonus on top of it.

---

## Every assumption that is still arbitrary

| assumption | value | where | status |
|---|---|---|---|
| `TARGET_HAIRCUT` | 0.35 | `pm_engine` | the number the product rests on. Fitted to nothing. |
| `BINARY_EXTRA_HAIRCUT` | 0.60 | `pm_engine` | unfitted |
| `DEFAULT_CORRELATION` | 0.35 | `pm_engine` | understates a crisis by construction |
| `RISK_AVERSION` λ | 1.0 | `pm_engine` | a choice |
| `SWITCH_THRESHOLD` | 0.03 | `pm_actions` | a choice |
| `RETAIL_ROUND_TRIP` | 40bp | `pm_engine` | a floor; real spreads mostly unobservable to us |
| `MAX_ROUND_TRIP` | 5% | `pm_engine` | a guard, not a measurement |
| `UNPRICED_NAV_TOLERANCE` | 10% | `pm_actions` | a judgement about how much NAV may be unknown |
| reliability bands | `[0.35, 1.0]` | `pm_evidence` | heuristic prior, `calibrated: False` |
| revision tilt band | ±20% | `pm_evidence` | heuristic prior |
| scenario definitions | .20/.35/.50 haircut | `pm_actions.SCENARIOS` | chosen before seeing results, not tuned to the goal |

The first one retires the moment the journal has ~50 resolved instructions. That
is the highest-value calibration available and nothing else is close.

## Every missing source (with a printed status code)

Full matrix and receipts: `docs/BUILD1/ANALYST_SOURCE_COVERAGE.md`,
`docs/BUILD1/analyst_source_probe_DKNG.json`. Reproduce with
`python scripts/probe_analyst_sources.py --ticker DKNG`.

| want | status | consequence |
|---|---|---|
| per-analyst target history (FMP `price-target-news`) | **402** | ΔTarget must come from our own ledger |
| FMP consensus / grades (legacy v3, v4) | **403** legacy path retired | — |
| FMP consensus / grades (current `stable`) | **402** premium | — |
| Finnhub `/stock/price-target` | **403** | — |
| Finnhub `/stock/upgrade-downgrade` | **403** | — |
| EODHD fundamentals (AnalystRatings, Earnings::Trend) | **403** | — |
| Polygon NBBO (real bid/ask) | **403** | spread stays `unavailable`, cost is an assumption |
| FDA / PDUFA / readouts / offerings / 13D-G / lockups | **no source found** | hand-entered under `catalysts:` only |
| Alpha Vantage `OVERVIEW` (second target) | **200** | available, **not wired** — 25 req/day vs a 45-name book |
| Finnhub `/calendar/earnings`, `/stock/earnings` | **200** | this is the catalyst layer |
| Finnhub `/stock/recommendation` | **200** | dated rating history, better than Yahoo's — not yet wired |

---

## What Murat must enter

Nothing else in the product moves until this is done. Everything below is
`SIMULATED` until it is.

Edit `backend/data/murat_book.yaml`, per position:

1. **`shares:`** — the actual count from the broker. Not an estimate. This is
   the only field that marks to market.
2. **`cost_basis:`** — **per share**, not total.
3. Delete `dollars:` (ignored once shares exist).

Then at the top of the file:

4. **`cash:`** — the real cash balance.
5. **`confirmed: true`**.

If only the dollar amount is known,
`python -c "from backend.services.pm_engine import shares_from_dollars; print(shares_from_dollars(5000, 24.86))"`
does the arithmetic and prints a warning. It is an attended helper and is never
called by the engine — a silently inferred share count is a placeholder wearing
a fact's clothes.

**Dry-run first.** `docs/BUILD1/example_confirmed_book.yaml` is a worked example
with invented share counts:

```bash
python scripts/morning_brief.py --book docs/BUILD1/example_confirmed_book.yaml
```

A confirmed book that cannot mark to market is rejected at load with the reason,
and nothing is computed.

Also outstanding, unchanged from BUILD-1: **the trade history behind the 25k→45k
year** (B7). Both are private operational data per
`docs/BUILD1/PRIVATE_DATA_POLICY.md`.

---

## Example confirmed morning report

`docs/BUILD1/example_confirmed_report.txt`, generated from the example book
against live data on 2026-08-10. Header:

```
PORTFOLIO $48,382   invested $45,882   cash $2,500
          valued on: MIXED — some positions could not be marked to market  [degraded]

12-MONTH VIEW (BASE)   median $51,531   p25 $41,851   p75 $64,420
                     P(reach target) 3.0%    P(below floor) 3.6%    P(below ruin) 0.1%
                     expected max drawdown -23.2%   P(worse than -50%) 1.1%
                     required return for the target +106.7%

MODEL SENSITIVITY — the same book, three sets of assumptions
  scenario       haircut   corr  vol x     median  P(target)  P(<floor)  P(<ruin)  E[maxDD]
  conservative      0.20   0.55   1.15    $46,773       4.6%      13.2%      1.3%   -32.0%
  base              0.35   0.35   1.00    $51,531       3.0%       3.6%      0.1%   -23.2%
  optimistic        0.50   0.25   1.00    $54,786       3.0%       1.4%      0.0%   -19.3%

AARD         733    $7.50    $5,494   -25.1%  11.4%   0.0%   -13.3%  SELL  $-5,496
APLT       3,636      n/a    $2,909      n/a   6.0%   6.0%      n/a  REVIEW
  ! no live quote: APLT — 6.0% of NAV is unpriced (tolerance 10%)

TODAY'S TICKETS
```

APLT is the whole point of the design in two lines: it cannot be priced, so it
is **REVIEW** and never SELL, and because it is 6% of NAV — inside the 10%
tolerance — the rest of the book stays actionable, with the uncertainty named.

---

## Tests

```bash
python -m pytest backend/tests/ -v -m "not slow"        # full fast suite
python -m pytest backend/tests/test_pm_build11.py -v    # the acceptance tests
```

`backend/tests/test_pm_build11.py` — the BUILD-1.1 acceptance suite. Every test
pins a *property* rather than a number, because the numbers are supposed to move
and the properties are not. Coverage of the twenty required items:

| # | requirement | test |
|---|---|---|
| 1 | +20% mocked price changes NAV with no book edit | `test_1_a_price_move_changes_nav_without_touching_the_book_file` |
| 2 | confirmed position without shares rejected | `test_2_*` (+ parametrised bad share counts) |
| 3 | price-only held name → REVIEW never SELL | `test_3_*` |
| 4 | missing / malformed / NaN target → REVIEW | `test_4_*`, `test_4b_*` |
| 5 | analyst API exception → REVIEW | `test_5_*`; stale → downgrade, `test_5b_*` |
| 6 | same alpha, higher vol → same E[R], wider dist | `test_6_*`, `test_6b_*`, `test_6c_*` |
| 7 | higher vol worsens every risk metric | `test_7_*` |
| 8 | replacement cost units reconcile | `test_8_*`, `test_8b_*`, `test_8c_*` |
| 9 | candidate is in the proposed portfolio | `test_9_*`, `test_9b_*` |
| 10 | buys/sells reconcile inside cash | `test_10_*`, `test_10b_*` |
| 11 | `max_names` enforced | `test_11_*`, `test_11b_*` |
| 12 | `min_cash` enforced | `test_12_*` |
| 13 | mode changes risk only, never evidence | `test_13_*` |
| 14 | unconfirmed → `actionable: false` | `test_14_*` … `test_14e_*` |
| 15 | missing history ≠ perfect freshness | `test_15_*`, `test_15b_*`, `test_15c_*` |
| 16 | revisions cannot exist without snapshots | `test_16_*` … `test_16d_*` |
| 17 | conservative/base/optimistic + downside | `test_17_*`, `test_17b_*`, `test_17c_*` |
| 18 | existing PM tests green | `test_pm_engine.py`, updated where the semantics changed |
| 19 | full suites green | see below |
| 20 | no execution path added | `test_20_*` greps every PM module |

Plus the execution layer (`test_p4_*`) and the catalyst layer (`test_18*`,
`test_19*`).

Four v1 tests changed **semantics**, not just values, and the changes are the
point: `test_the_haircut_actually_bites` now asserts the haircut lands on the
*expected return* rather than the median; `test_the_distribution_is_one_lognormal`
asserts mean > median rather than mean floating above a pinned median;
`test_no_data_is_a_review_not_a_sale` uses `decisionable`; the replacement tests
compare certainty equivalents.

---

## The next three highest-value product tasks

**1. Fit `TARGET_HAIRCUT`, and retire the assumption.** Every probability the PM
prints is a linear function of a number chosen by hand. The journal already
freezes price, target, dispersion, coverage and drift with every instruction, so
the estimator is a matter of waiting for resolutions and then running it. Until
then the scenario band is doing the honest work of admitting we do not know it —
but a band is not a measurement. *Blocked only on elapsed time and a confirmed
book.*

**2. The opportunity funnel (P3).** The radar still ranks Murat's 34-name
watchlist and labels itself `opportunity_scope: watchlist only`. The engine
cannot find what is not already on the list, which is most of the market. The
staged design is right — universe → liquidity/data screen → cheap features →
top ~200 deep enrich → top ~20-40 → into the *same* joint optimiser that now
exists. The optimiser side of that is already built and tested; only the funnel
is missing.

**3. Wire the second target source and the dated rating tape.** Alpha Vantage
`OVERVIEW` gives an independent consensus target (200, free) and Finnhub
`/stock/recommendation` gives rating counts with **real dates** (Yahoo's have
none). Two sources means disagreement becomes visible, `source_count` stops
being 1, and the reliability discount gets something real to key on. The blocker
is a quota ledger — Alpha Vantage is 25 requests/day against 45 names — and this
programme's house failure mode is exactly the collector that runs green and
silently returns nothing, so it needs the budget guard before it needs the
wiring.

Deferred and still deferred: the G8 capacity ladder (institutional, background
per the pivot), PF8, T4b, N3b.

---

## What did not change

The research side is untouched. NIGHT-9's conclusions stand as written,
including the standing wording that **rank-IC may describe ordering but may not
corroborate a null money result**, the N2 corrigendum (distress 3.40×, issuance
2.22×, union 1.49×, accruals 1.05×), and the note that the N1B phase axis is not
trustworthy. G8 remains built, calibrated, and unpointed at the book.

The engine still never trades. The LLM still never sizes. The ruin number still
prints beside the dream number — and after BUILD-1.1 it prints three times, once
per scenario.
