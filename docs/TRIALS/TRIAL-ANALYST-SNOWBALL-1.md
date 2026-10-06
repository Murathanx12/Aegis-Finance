# TRIAL-ANALYST-SNOWBALL-1: after a 90-day quiet spell, does the first price-target raise start a snowball, and does the stock drift after it? (UNSIGNED DRAFT)

> **STATUS: UNSIGNED DRAFT, 2026-10-06. NOT REGISTERED.** Written by the C12 builder from
> `docs/research_notes/2026-10-06/snowball_and_theory_objects_2026-10-06.md` §1. It is **not**
> in `rule_experiments`, carries no registration receipt, and **no outcome has been read on the
> CRSP/IBES instrument for this construction**. The orchestrator or the owner signs it (adds the
> SHA-256 + UTC receipt and the registry row) or rejects it. Until it is signed, nothing below
> may be run as a decision. The linter output is at the end; its verdict is
> `UNPOWERED_AT_REGISTRATION` for the return leg, and that is the honest state of this design.

Licence: **`PRODUCT_EXPERIMENT`-shadow grade, at most.** The follow-through leg is a
descriptive measurement of analyst behaviour (no cost model, no capital consequence). The return
leg is **underpowered as a `RESEARCH_CLAIM`** (see the power section and the linter), and four
closed siblings say it most likely dies against the market the same way. A pass here makes the
return leg a candidate for a forward shadow log, nothing more. Nothing here may be proposed as a
`CAPITAL_CANDIDATE` or a `RESEARCH_CLAIM`.

## Where the lead comes from, and why it is a hypothesis

- Owner's framing (2026-10-06 roadmap §5 row 28, "first-mover snowball"): one analyst breaks a
  long silence, others follow over the next quarters, and the price follows the crowd.
- `docs/research_notes/2026-10-06/snowball_and_theory_objects_2026-10-06.md` §1.4 counted the
  event on the **yfinance** instrument (`backend/data/optimus/analyst/target_revisions.parquet`,
  2011-12-08 .. 2026-10-05): **24,323** quiet-break raises (90-day gap, >= 90 days of prior raise
  history), 2,668 tickers. It also **read the follow-through outcome** on that instrument:
  P(>= 2 other firms raise within ~63 sessions) = **35.9%** (18.0% within ~21 sessions), rising
  from ~18-33% before 2020 to 35-45% after. No return outcome was read for this construction on
  any instrument.
- Nearest closed sibling (same mechanism, different instrument):
  `docs/research_notes/2026-09-30/bridges_and_conditionals_2026-09-30.md` §2: the CRSP-bridge
  `first_mover_raises` (`crsp_pit_bridges.first_movers(raises, gap_days=30)`) as a monthly
  cross-sectional book vs a matched twin and the market: CANNOT_DISTINGUISH (twin t 3.4-3.6 that
  evaporated against the market). "This closes these implementations."

Resurrects: first_mover_raises — new instrument: a 90-day quiet-gap event (not a 30-day monthly book), read as an event-count probability and a next-session event study conditioned on nothing after t0, on the CRSP/IBES bridge
Resurrects: ANALYST-SKILL-1 — new instrument: none on the weighting side; this draft does NOT re-test broker-skill weighting (ADOPT_AT_TRIVIAL_EFFECT, not funded), it only reuses `pit_features.firm_reliability` as a reported covariate resolved strictly before t0

**Honest prior.** Follow-through: plausible (analysts herd; the yfinance read already shows a
36% two-follower rate, which is a base rate, not yet an excess over the name's own activity).
Return: weak to null. `net_raises`, `first_mover_raises`, `ear_flow` and the two revision tilts
all produced real rankings against a matched twin that died against the market; nothing in a
longer quiet gap obviously escapes that.

## Hypothesis

For US common stocks on the CRSP/IBES bridge, the first 12-month price-target raise that ends a
>= 90-calendar-day spell with no raise by any broker (t0) is (1) followed by raises from at least
two OTHER brokers more often than a matched non-first-mover raise is, and (2) followed by a
positive market-relative return from the first session after t0 is public, measured with no
information after t0.

## Exact construction (frozen at signing)

- **Instrument**: `backend/services/crsp_pit_bridges.py` / `crsp_event_bridge.py` on the WRDS
  IBES detail file (`tr_ibes.ptgdetu` via `wrds/bulk/ibes__ptgdet.parquet`, 12-month horizon,
  USD, `usfirm = 1`), IBES ticker -> permno through the `ibcrsphist` row active ON the event day
  (lowest score). Event day = max(anndats, actdats); usable from the next business day. Sign of
  a target change = vs the same broker's previous 12-month target <= 365 days old
  (`crsp_event_bridge.target_signs`). The yfinance file is used for nothing but the sizing
  above.
- **t0 flag**: `crsp_pit_bridges.first_movers(raises, gap_days=90)` (the existing function,
  `backend/services/crsp_pit_bridges.py:318`, parameter changed from its default 30), PLUS the
  coverage-start exclusion: the permno has a raise history of at least 90 days before the quiet
  window (a name entering coverage has no quiet spell to break). The flag reads only
  `[day - 90, day)`.
- **Follow-through leg (primary 1)**: count of DISTINCT brokers other than t0's broker with a
  raise on the same permno whose usable date falls in sessions (t0, t0 + 21] and (t0, t0 + 63]
  (CRSP trading calendar, not calendar days). Binary outcomes `snow21 = count >= 2`,
  `snow63 = count >= 2`.
- **Return leg (primary 2)**: entry at the OPEN of the first CRSP session after the usable date;
  held 21 and 63 sessions; market = FF `mkt + rf` over the same sessions; reported gross and net
  of one round trip at max(Corwin-Schultz at the last month-end, flat band) — the house
  `hyp_insider_events` convention. **Never conditioned on the follow-through outcome** (that is
  information after t0).
- **Aggregation**: per entry month, mean over events; statistic = mean over months; SE on
  non-overlapping 3-month blocks for the 21-session leg and on non-overlapping 63-session blocks
  for the 63-session leg (the blocking follows the horizon; `feedback_a_t_whose_bias_depends_on_the_swept_parameter`);
  MDE = 2.8 x SE printed beside every t.
- **Reported, never deciding**: by year (keyed on the HOLD month), leave-one-year-out worst,
  share of total by date, t0 broker's `firm_reliability` weight resolved strictly before t0
  (`asof = t0`, `RESOLVE_DAYS = 92`), the 2012-2016 thin-coverage stratum separately.

## Control

1. **Matched non-first-mover raises** ("chasers"): raises on the same permno by brokers who raised
   inside a window that was NOT quiet (another broker raised in the 90 days before), same
   calendar month as t0 where one exists, else same quarter. Mirrors the `lead`/`chase` split of
   `crsp_pit_bridges.analyst2_panel`.
2. **Random matched raise dates**: size x vol x 12-1 momentum cell-matched raise events, same count,
   drawn with a seed outside every seed used on this board (session protocol item 9).

Primary 1 is the difference `P(snow63 | t0) - P(snow63 | control 1)`; primary 2 is the t0
return minus the market, with the control-1 return printed beside it.

## Windows

- Design: t0 usable 1999-02-22 .. 2008-12-31 (fixes the sign and the 90-day gap's base rate; no
  parameter is tuned on it beyond what is frozen here).
- Validate: 2009-01-01 .. 2016-12-31, **read once, in one sitting.**
- Late: 2017-01-01 .. 2024-12-31, read last, never decides.
- No forward accrual is needed for the historical read. The only route to an independent
  confirmation is forward: t0 events after the signing date, logged as a shadow book.

## Power (stated before any read)

- Follow-through leg: on the yfinance sizing, 19,207 events 2017+ over 118 months, base rate 0.36;
  with month blocks a 5pp shift is resolvable (note §1.4). It is not the leg that needs this
  registration.
- Return leg: the sibling closures measured gaps against the market of about -0.6%/month; an
  effect under roughly 0.3-0.5% per 21 sessions should be assumed undetectable on one historical
  pass. The linter (below) agrees and is harsher, because it caps one 21-session outcome per
  month of calendar.

Machine-readable (R13), for the RETURN leg:

- declared_effect_size: 0.4pp
- event_frequency_per_year: 1500
- outcome_dispersion: 12pp
- outcome_horizon_days: 21
- dependence_unit: calendar month of t0 (raises in the same month share the market and earnings-season news)
- corpus_years: 26

`event_frequency_per_year = 1500` is the yfinance count (24,323 over ~14.8 years ≈ 1,640/yr)
rounded down; the CRSP/IBES count must be printed from labels only (no outcome) before signing.
`outcome_dispersion = 12pp` is the house `single_name` preset, NOT measured on this construction.
`cross_sectional_k` / `cross_sectional_rho` are deliberately not declared: rho must be measured on
a policy-free surrogate (e.g. same-month 21-session excess returns of random matched raise dates)
before it can be claimed, and that measurement is the one step that could move this leg from
UNPOWERED to RESOLVABLE. It is owed before signing.

## Slice declaration

- slice_purpose: EXPLORE
- slice_period: 1999-02-22 .. 2024-12-31
- selection_period: NONE (the 90-day gap comes from the owner's quarter framing; it was not fitted on returns)
- hypothesis_source: first_mover_raises CRSP-bridge closure (bridges_and_conditionals_2026-09-30 §2) and the yfinance follow-through count (snowball note §1.4)
- hypothesis_source_period: 1999-02-22 .. 2026-10-05

EXPLORE, not CONFIRM, because the 30-day sibling already read 1999-2024 returns on this same
bridge and the follow-through base rate was read on yfinance 2012-2026. Nothing in this window
can be written up as an independent confirmation.

## The look-ahead traps, closed in writing

1. **t0 never peeks.** `first_movers` reads only `[day - gap, day)`. The follow-through count and
   the return are never joined back into the t0 definition; "the real snowball start" is never
   chosen retroactively from a cluster's best performer.
2. **No conditioning on followers.** Primary 2 is computed on EVERY t0 event, whether or not it
   snowballed. A "snowball-conditional" return is a report-only row and is labelled as using
   information up to t0 + 21/63 sessions.
3. **The reputation prior resolves before t0.** Any broker-reliability covariate calls
   `pit_features.firm_reliability(asof = t0)` with its `RESOLVE_DAYS = 92` margin: a claim
   counts only once its outcome was knowable before t0, not merely dated before it.
4. **The link is dated.** IBES ticker -> permno uses the `ibcrsphist` row active on the event day,
   never the latest mapping.
5. **Coverage start is not a quiet spell.** The 90-day prior-history requirement removes 10.5% of
   naive candidates on yfinance; a run that drops it is a different trial.

## Decision rule (validate read once)

| outcome | condition | verdict |
|---|---|---|
| snowball exists | primary 1 > 0 with t >= 2 on month blocks in validate, design sign the same, strict majority of validate years > 0, leave-one-year-out worst > 0 | `CANDIDATE` (behavioural fact, descriptive context only) |
| return candidate | primary 2 net of costs > 0 with t >= 2 in validate (63-session blocks for H63), design > 0, majority of years > 0, LOO worst > 0, AND > 0 against the market (not only the control) | `CANDIDATE` for a forward shadow log (`PRODUCT_EXPERIMENT`, frozen contract), nothing else |
| underpowered | mean > 0 but the t / years / LOO condition fails and the MDE exceeds the declared effect | `CANNOT_DISTINGUISH` |
| refuted at this power | mean <= 0, or t < 2 with MDE <= the declared effect | `FAILED_VARIANT` (this construction); `RETIRED_FROM_CURRENT_SEARCH` for the return leg |

Never `STOP`; `MECHANISM_REJECTED` is not available to a single construction.

## What this trial may NOT do

- It may not be run as a decision before it is signed.
- It may not select the gap (60/90/120 days), the horizon or the follower threshold after any
  read; a different value is a successor trial.
- It may not condition the return leg on anything after t0.
- It may not feed `arena_composite` or any book as a weight; a candidate arrives as its own
  `PRODUCT_EXPERIMENT` shadow book.
- It may not describe the historical read as independent confirmation.

## Corpse check / R13 linter output (run 2026-10-06 on this draft)

Pasted verbatim below. Reading it:

- **No corpse blocks it.** The two nearest neighbours (0.226, 0.213) are below the 0.30 block
  line and are both the skill/forecaster preregs, not the first-mover closure (which lives in a
  research note, not the linter's corpus: the `Resurrects:` line above is on the record anyway).
- **R13 refuses the return leg as a claim: `UNPOWERED_AT_REGISTRATION`, exit 1.** Capped at one
  independent 21-session window per month for 26 years, the corpus supplies 312 observations
  against 7,064 needed; the smallest resolvable effect is 1.9pp per 21 sessions, about 4-5x
  anything a sibling ever showed. This is the linter saying, in numbers, what the licence line
  says in words: the return leg is `PRODUCT_EXPERIMENT`-shadow grade and cannot be a
  `RESEARCH_CLAIM` on this design. The cap treats every event in a month as one observation; a
  MEASURED `cross_sectional_rho` (owed, above) is the only declared route that could credit the
  cross-section, and it must be measured before signing, not assumed.
- **The signer's choice**, stated so it is not made by silence: (a) sign the follow-through leg
  alone as descriptive context (no registration is strictly needed for it, per the note §1.8),
  and log the return leg forward as a shadow series; or (b) measure rho, re-lint, and sign only
  if the linter returns RESOLVABLE; or (c) reject. The builder recommends (a).

```
$ cd "C:/Users/mrthn/Aegis module" && .venv/Scripts/python.exe scripts/lint_prereg.py <this file>

TRIAL-ANALYST-SNOWBALL-1.md: UNPOWERED_AT_REGISTRATION  (vs 358 prior experiments)
  R13: resolving a 0.4pp effect at dispersion 12pp needs **7064** independent observations. At 1.5e+03 per year over 26 years the corpus can ever supply **312** (R13b: capped from 39000 — your 1.5e+03 events/yr overlap 125.0x at a 21-day horizon, where only 12.0 independent windows fit in a year). This design cannot resolve this claim, and running it would produce a NOT_DETECTABLE that says nothing about the world. The smallest effect this corpus could resolve is **1.9pp** — either declare an effect at least that large AND defend it from turnover, cost, capacity and drawdown consequence, or change the conditioning unit (R14: events, not regimes).
  R13: n_required 7064  n_available 312  smallest resolvable effect 1.9pp
   [near     ] 0.226  prereg    REGISTERED             PREREG_ANALYST_SKILL_1
   [near     ] 0.213  prereg    REGISTERED             PREREG_REVISION_FORECASTER_1
exit=1
```
