# G4 V1 — the expectation layer, and the measurement that justifies building it first

**2026-08-16.** Real records, real PIT timestamps, on the highest-sample event
family. Read-only, bounded, manifested. No production path, lane, NAV, live
registry or deployment touched.

---

## 1. Why this had to come before the factory, measured rather than argued

The winner/matched-loser factory asks an LLM what observable difference explains
why A beat B. The worry was that without an expectation layer it would keep
rediscovering *"companies with good earnings go up"* — an announcement fact,
already in the price, not tradable.

That worry is now a number. **60,402 records, 2006–2019**; 58,066 with both a
surprise and a reaction:

| the claim | events | mean next-session reaction |
|---|---|---|
| **positive EPS** — an ANNOUNCEMENT fact | 51,384 | **+0.25%** |
| **beat consensus by >1σ** — a SURPRISE fact | 28,010 | **+1.88%** |

Seven and a half times the signal, from the same events, by knowing what was
expected. The first row is what the factory would have found without G4, and it
is worth nothing.

**And it is stable.** The layer was built and checked on 2015 alone before the
other thirteen years were collected:

| | 2015 only | full 2006–2019 |
|---|---|---|
| announcement | +0.19% | +0.25% |
| surprise >1σ | +1.92% | +1.88% |
| corr(surprise, reaction) | +0.199 | +0.194 |
| beat rate | 61.9% | 64.1% |

Thirteen unseen years moved nothing. That is the check that distinguishes a
working join from one that happened to line up on the year it was debugged
against.

## 2. The layer works, checked against facts nobody here chose

Surprise deciles against the first tradable session's return:

```
 D1  surprise -3.00   mean reaction  -4.47%
 D2           -1.00                  -2.10%
 D3           -0.33                  -2.92%
 D4           +0.00                  +0.45%
 D5           +0.50                  +0.05%
 D6           +1.00                  +0.34%
 D7           +1.50                  +1.60%
 D8           +2.00                  +1.58%
 D9           +3.33                  +2.16%
 D10          +6.00                  +3.24%

 corr(scaled surprise, reaction) = +0.199
 beat rate = 61.9%
```

Monotone but for D3, correlation in the published range, and a **61.9% beat
rate** — the canonical expectation-management stylised fact. Nothing here was
tuned; if the pipeline were mis-joined, the beat rate would not land on the
number the literature reports and the deciles would not order.

**This is not a finding and must not be quoted as one.** It is the immediate
announcement response, which is well documented and not tradable — the reaction
is measured *starting at* `tradable_at`. Its only job is to prove the plumbing
carries information, and it does that.

## 3. Four clocks, because the research lives in the gaps between them

```
expectation_asof   what the market believed, and WHEN
first_public_ts    when the fact became public
observed_at        when OUR source recorded it     -> disclosure delay
tradable_at        the earliest we could have acted
```

`first_public_ts − expectation_asof > 0` is what makes a surprise a surprise, and
`validate` refuses the record if it is not **strictly** positive.
`observed_at − first_public_ts` is the disclosure delay — across the full
corpus **median 0.45h, p90 10.9h, max 740 days**. It is the whole subject of
actor intelligence, and the spread is the point: AAPL's Q1 2015 was recorded
4m48s after its 16:30 announcement; its Q2 not until 07:43 the next morning.

The 740-day tail is a data-quality flag, not a defect in the record: IBES
backfills some actuals long after the fact. Those records are still valid —
`observed_at ≥ first_public_ts` holds — but any study of *our* latency must
treat `observed_at` as IBES's clock rather than the world's, and a backfilled
row is evidence about the vendor's process on that name.

A record that cannot order these is **refused, never repaired**. A timestamp
guessed to make a record valid is how look-ahead enters a dataset, and it enters
looking exactly like diligence.

## 4. The guard caught a real error in its first run

The first version set `tradable_at` to the 09:30 open whenever a company
reported before 16:00. For companies that report *during* the session that is
**before the announcement**, and `validate` refused 57 of them rather than
letting a negative reaction window through.

That is precisely the case where an off-by-one hands you the move you are trying
to predict. Now: after-hours → next session's open; pre-market → same-day open;
intraday → the announcement time itself. `0 refused` after the fix, on all 4,697.

Second thing the run corrected: the refusal report grouped by message prefix,
which contains a timestamp — so one bug reported as 57 distinct reasons with
count 1 each. **A refusal report that hides the pattern is barely better than
silence.**

## 5. PIT rules, each paid for by a known trap

1. **Unadjusted IBES files** (`statsumu_epsus`, `actu_epsus`). The adjusted files
   apply splits *retroactively*, so a consensus read today is not the number
   that existed then — and the error correlates with which companies split,
   which is to say with past performance.
2. **Consensus strictly before the announcement** (`statpers < anndats`).
3. **Fiscal period matched on `fpedats`, not the `fpi` code.** The fpi for one
   quarter changes as the calendar moves — visibly, in the data: AAPL's
   2015-03-31 quarter is fpi `8` a year out and `6` a month out. Matching the
   code would silently pick a different quarter.
4. **`tradable_at` from the exchange calendar** (`crsp.dsi`), not a weekday rule
   a holiday breaks.
5. **The identifier link resolves per announcement date.** The first version
   bound it to one `asof` for the whole run: that drops every company delisted
   before year-end AND resolves survivors at a date the event did not happen on.
   Cusips are reused — that is why `stocknames` carries validity intervals — so
   a link at the wrong date attaches another company's prices to an event, and
   the result looks like data. Ambiguous intervals resolve to **nothing**, not
   to the first match.

## 6. UNKNOWN is a value, and it has to be said out loud

Every field may be unknown; none may be *silently* absent. A `None` with no
entry in `unknown_reasons` is refused. One line per missing field, and it buys
the difference between "we looked and there is none" and "nobody wired this up".

The case that proves it: **`ibes.det_guidance` appears in
`information_schema.tables` with exactly the columns `guidance_state` wants —
and selecting from it returns `permission denied for schema tr_ibes_guidance`.**
It is a view over a source this subscription does not include. Appearing in the
catalogue is not being entitled to it, and a collector that had assumed
availability from the listing would have shipped a guidance column that silently
never populated. So `guidance_state` is UNKNOWN with that sentence as its stated
reason, in one place, for whoever asks next.

`options_implied_move` is UNKNOWN for the same reason, differently: the daily
`vsurfd` pull is bounded to WM0's eighteen ETFs for `IV-ORACLE-GAP-1`, so no
single-name surface exists yet.

## 7. Coverage, with the denominators visible

```
2015:   17,268 IBES announcements
         4,697 with >= 10 estimates   (12,571 dropped as thin coverage)
         4,697 records written, 0 refused
         4,636 surprise resolvable    (61 have zero/absent dispersion)
         4,584 with a price reaction

2006-2019 total:  60,402 records across 14 years, 0 refused
                  58,066 with BOTH a surprise and a reaction (96.1%)
```

The `>= 10 estimates` floor is a data-quality bound, not a parameter: below it
`stdev` is a statistic about three opinions. It is declared in the manifest and
applied *after* the count above, so the denominator is visible rather than
implied.

## 8. What V1 deliberately does not do

* **No semantic fields.** `semantic_expected_state`, `semantic_actual_state`,
  `semantic_surprise`, `already_priced_estimate` stay None. The schema carries
  them so a later sourced, PIT-blinded LLM pass has somewhere to land; mixing
  that into the collector would make the numeric layer's provenance unauditable.
  Anything an LLM populates must carry `source_ids` or the record is refused.
* **No other event family.** Earnings first because it is the highest-sample one
  with a published pre-event expectation.
* **No signal, no trial, no pre-registration.** This is a data layer. The
  decile table above is a plumbing check and is not evidence of anything
  tradable.
