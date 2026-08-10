# Optimus Portfolio Manager v1.1 — what changed and why

BUILD-1.1 is a **product-correctness** build. It adds almost no capability. It
fixes the six things that made v1's dollar figures untrustworthy, plus four
found while fixing them, and it builds the analyst spine that B1 required.

Parent: `0c3f170` (PM v1). Read `docs/PORTFOLIO_MANAGER_v1.md` first for the
design; this documents only the deltas.

---

## The six P0 defects

### P0.1 — the book did not mark to market

`daily_brief` computed invested value and every current weight from
`Position.dollars`, a static number in a YAML file. `shares` existed in the
schema and was read by nothing.

The consequence is worse than it sounds: a book could report "$45,000"
indefinitely while its holdings halved, and every weight, every ticket size and
every wealth probability derived from it would be arithmetically consistent and
completely wrong.

Now: `shares × live price` is the authoritative value of a confirmed position.
`mark_position` has an explicit precedence — shares×price, then shares×cost
basis (flagged `no live quote`), then the `dollars` placeholder (unconfirmed
books only, flagged `does NOT move with the price`). `validate_book` rejects a
confirmed book whose positions lack a finite positive share count, and
`load_book` raises `BookError` on it. `shares_from_dollars` exists as an
attended helper and is deliberately not called anywhere in the decision path.

### P0.2 — a missing feed could become a SELL

`enrich` returned one flag, `available`, which meant "we got a price". A name
with a price and no consensus target was `available: True` → no distribution →
`target_weight` 0 → `action_for` read the zero as a view → **SELL**.

Now there are four states, and they are separate because they were always
separate facts:

```
market_data_status    ok | missing
analyst_data_status   ok | stale | missing | error
distribution_status   ok | no_target | no_price
decisionable          all three usable
```

A held name with `decisionable: False` produces **REVIEW** and a zero ticket.
A candidate with `decisionable: False` produces **SKIP** and is never bought. A
SELL now requires a real negative view — the expected return did not survive the
haircut, or the name lost its slot to something better. Both are decisions;
an outage is not. Malformed and NaN targets are routed to `missing`, not to
zero.

### P0.3 — volatility manufactured expected return

This was the most consequential. v1 set the lognormal's **median** to
`haircut × upside` and then reported its **mean**, which is larger by
`exp(σ²/2)`. A 90%-vol name got a ~40% higher expected return than a 30%-vol
name off the same analyst target — and then a larger Kelly weight for it. In a
book of speculative biotech, quantum and crypto proxies, that is a machine for
buying variance and calling it alpha.

Now the street target, after haircut and reliability, **is the expected value**:

```
E[R] = haircut × implied upside × reliability × revision tilt      (σ-free)
m    = ln(1+E[R]) − σ²/2      so  exp(m + σ²/2) − 1 == E[R]  for every σ
```

Raising σ pushes the median down and the tails out and leaves the mean where the
evidence put it. Kelly still penalises the variance through its denominator,
which is the correct and only channel. `expected_return()` is a separate
function so the one number the product rests on is built in one place, and
`interpretation` states plainly that the target is read as an expected value —
one answer, not three.

**This changes the headline numbers.** On the reconstructed book the base median
moved from ~$64.5k to ~$48.5k and P(reach $100k) from 19.8% to ~1.7%. The old
numbers were the convexity of an unvalidated assumption.

### P0.4 — the replacement edge mixed units

v1 computed `score(B) − score(A) − 0.004` and labelled it "net of a 40bp round
trip". The scores are arbitrary analyst-alpha units; 40bp is a return. Rescaling
the score would have silently rescaled the cost away.

Now everything is in expected-return units:

```
replacement_edge = CE(candidate) − CE(holding) − switching cost
CE = μ − λσ²/2                                            (λ = 1.0)
```

`alpha_score_delta`, `expected_return_delta`, `risk_delta` and
`estimated_switch_cost` are reported separately. `correlation_delta` is `None`
with a reason — the book assumes one average pairwise correlation, so there is
no per-pair estimate to difference, and MISSING is not zero.

### P0.5 — two lists pretending to be a portfolio

v1 sized the holdings, ranked the watchlist separately, then labelled a few
pairs as switches afterwards. "BUY KYTX funded by AARD" did not mean the book
had been re-solved without AARD, and the wealth simulation never saw KYTX at
all.

Now `build_target_portfolio` solves **one** portfolio over holdings ∪
candidates. Three classes of name: **frozen** (held, not decisionable — keeps
its current weight, consuming a slot and budget), **eligible** (competes for
`max_names` slots on Kelly weight), **excluded** (candidate we cannot see).
`funding_plan` decomposes the solved delta into which sale pays for which
purchase, and the replacement table is that decomposition. The wealth
simulation runs the proposed book.

`max_names` is now a real constraint — it was defined in `MODES` and read by
nothing. `min_cash` binds through the allocation budget.

### P0.6 — a three-significant-figure probability off an unfitted assumption

`wealth_scenarios` runs conservative / base / optimistic and prints them
together, with median, P(target), P(<floor), P(<ruin) and E[maxDD] in each.
Because μ is linear in the haircut, scaling it is exact and no data is refetched.

The scenarios are not tuned to flatter the goal: the optimistic arm still takes
less than half the street's word (haircut 0.50), and the conservative arm raises
correlation to 0.55 and volatility 15%.

**A finding fell out of this.** For the reconstructed book the conservative arm
prints a **higher** P(reach $100k) than the base arm while ending poorer in the
median and ruined more often. That is not a bug: $45k → $100k in twelve months
needs +122%, which is reached by variance, not by drift. The brief now sets
`volatility_dominates_target` and says so in words, because a reader who saw
only "conservative: 3.2%" would take the wrong comfort from it.

### P0.7 — an unconfirmed book looked actionable

`actionable: false` on the API. The CLI prints
**`SIMULATED TICKETS — BOOK UNCONFIRMED — DO NOT EXECUTE`** in the same position
the confirmed run prints `TODAY'S TICKETS`, so the two states cannot be confused
at a glance. `actionable_blockers` names each reason. The journal records every
row with `executed: false` and `actionable: false`.

---

## Four more defects, found while fixing those

**A junk quote was being charged as a cost.** Live on 2026-08-10, Yahoo returned
AARD at bid 5.48 / ask 9.60 — **in a size of two shares** — while the stock last
traded at 7.50. Doubled into a round trip that is 55%, and it made every
replacement comparison touching the name meaningless (observed switch costs of
0.60–0.83 in the live brief). A quote is now accepted only if it brackets the
last trade within 1%, is under 500bps wide, and shows at least one round lot.
Otherwise the spread is `unavailable` — a fact — rather than a number, which
would not be. Round-trip cost is capped at 5% with a note that a cost that high
is a reason not to trade the name, not a number to charge inside a comparison.

**The intraday range was sitting next to the liquidity fields** where it could be
read as a spread. Renamed `intraday_range_pct` and carries
`"a RANGE, not a quoted spread, and not a cost"`.

**The optimiser churned, because it does not charge trading costs.** The
no-trade band is now cost-aware: `band = REBALANCE_BAND × (round trip / 40bp)`,
so a name five times more expensive to trade must drift five times further
before it is touched. The pair-level check remains and is now labelled honestly
— a `DISSENT` row means the plan is making a trade whose own economics do not
clear the hurdle, and `model_status` counts them.

**Suppressed trims could fund purchases that had no cash behind them.** The band
and the minimum ticket kill a $200 funding trim as happily as a $200 top-up, so
a plan could emerge with $4,000 of buys funded by $3,800 of sells and no cash.
`enforce_cash_constraint` scales the buys to what the sales actually raise and
reports the reconciliation.

---

## Four more from the silent-fragility audit

The discipline skill was run over the diff (it adds collectors, fetchers and
`try/except` — its trigger). Three of these would have run green forever:

**`_vol` fabricated a volatility and cached it permanently.** Every exception
was swallowed, `FALLBACK_VOL = 0.65` substituted, and stored in a
process-lifetime dict. Kelly weight is `μ/σ²`, so one transient failure
quartered a low-vol name's position for the rest of the run. Now: logged at
WARNING, recorded in `VOL_FALLBACKS`, surfaced in `model_status`, and **not
cached**.

**A failed binary-event check made the riskiest names bigger.** `_looks_binary`
returned `False` on exception, removing the 0.60 extra haircut. The failure mode
pointed at more risk, not less. Now recorded and printed.

**A 403 calendar looked exactly like a quiet quarter.** In a layer whose entire
purpose is that silence must not read as safety. Now `CatalystFetchError`,
never cached as empty, and `coverage()` grades itself `v0 DEGRADED` naming the
tickers whose calendars are UNKNOWN rather than empty.

**A corrupt ledger row vanished silently**, leaving a smaller but healthy-looking
history. Now counted and reported.

## New: the analyst spine (B1)

`scripts/probe_analyst_sources.py` calls every endpoint we hold a key for and
prints the status code. Results and receipts:
`docs/BUILD1/ANALYST_SOURCE_COVERAGE.md`,
`docs/BUILD1/analyst_source_probe_DKNG.json`. The short version:

- **per-analyst target history is not purchasable on any tier we hold** — FMP
  402 on both the legacy and current API, Finnhub 403, EODHD 403, Yahoo returns
  a target with no timestamp at all;
- a **second consensus target is free today** (Alpha Vantage `OVERVIEW`), but
  the free tier is 25 requests/day against a 45-name book, so it is recorded as
  available and deliberately **not** wired in;
- **earnings dates and surprise history are free** (Finnhub, 200);
- **a real bid/ask is not** (Polygon NBBO 403).

⇒ `backend/services/analyst_ledger.py`. Append-only, one observation per ticker
per day, and it computes the real `delta_target_7d / 30d / 90d` only when two
snapshots actually span the window — otherwise `None` with a reason string
beginning `MISSING`. There is no path through that function that manufactures a
revision from one observation. Seeded 2026-08-10 with 43 tickers.

`rating_drift_3m` is no longer described as a target revision anywhere. It
counts ratings.

## New: evidence completeness and reliability

`backend/services/pm_evidence.py`. v1 scored unknown freshness as `1.0` — the
maximum — so an uncovered name out-scored one upgraded yesterday. Unknown is now
`0.5` on every axis, and missing dispersion carries a penalty rather than a free
pass.

`reliability` is a bounded **discount** in `[0.35, 1.0]` on the expected return,
multiplicative in breadth, freshness, completeness, dispersion and source
staleness. It can never amplify. It is `calibrated: False` and will stay that
way until the journal has enough resolved decisions to fit it — but an
uncalibrated discount is strictly better than the implicit 1.0 that was there
before.

This is also how the analyst evidence finally reaches **sizing**. In v1 breadth,
freshness and revision momentum affected candidate ranking and had no effect
whatsoever on how large a position became. Now they discount μ, which is what
Kelly reads. `analyst_alpha` remains as a readable ranking score and is
explicitly marked `is_ranking_only: True` with the sizing path named.

## New: the catalyst calendar, v0 (B5)

`backend/services/pm_catalysts.py`. Earnings dates and estimates plus surprise
history from Finnhub (free, verified 200), and hand-entered events from a
`catalysts:` block in the book file — the only route by which a PDUFA date
reaches this engine today. Bucketed 0-7d / 8-30d / 31-90d in the brief.

The important part is `coverage()`: FDA/PDUFA dates, readout windows, offerings,
13D/G, lockups and investor days have **no entitled source**, and every call
says so. For a book holding APLT, NTLA and BHVN, an empty calendar reading as
"nothing is coming" would be the most dangerous thing this product could imply.

## New: MODEL STATUS

Every brief ends with a block a reader can scan in five seconds: book confirmed,
valuation basis and whether NAV is complete, decisionable vs REVIEW counts, mean
evidence completeness, the reliability discount, which analyst sources are
actually read, whether target-revision history exists, catalyst coverage, the
return-model grade, the scenario range for P(target), and the last refresh.

---

## Still assumptions, still fitted to nothing

| assumption | value | status |
|---|---|---|
| `TARGET_HAIRCUT` | 0.35 | the number the whole product rests on. Unfitted. |
| `BINARY_EXTRA_HAIRCUT` | 0.60 | unfitted |
| `DEFAULT_CORRELATION` | 0.35 | understates a crisis by construction |
| `RISK_AVERSION` (λ) | 1.0 | a choice, not a measurement |
| `SWITCH_THRESHOLD` | 0.03 | a choice |
| reliability bands | see `pm_evidence` | heuristic prior, `calibrated: False` |
| `RETAIL_ROUND_TRIP` | 40bp | a floor; real spreads are mostly unobservable to us |

## Not built

The **opportunity funnel** (P3) — the radar still ranks the 34-name watchlist
and says so (`opportunity_scope`). A market-wide staged funnel is the next
capability, not a correctness fix, and the stop rule put correctness first.

The **analyst reliability ledger** (P1.3) has its schema in the snapshot ledger
but no per-analyst identity to key on, because no entitled source provides one.
Until then reliability is `UNCALIBRATED`, not 1.0.
