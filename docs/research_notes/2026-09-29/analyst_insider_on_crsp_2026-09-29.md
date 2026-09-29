# Analyst, insider and earnings-event rules on CRSP, 1991-2024: nothing survives the market (2026-09-29)

Licence `PRODUCT_EXPERIMENT`. $0.00, no LLM, no network, no broker call. No book, ledger row or earlier
receipt was changed. No shadow contract was registered: nothing met the decision line. Every number below
is in a receipt under `backend/data/optimus/crsp_rebuild/`:

- bridge `event_bridge_EB_2026-09-29T1055Z.{parquet,json}`
- flat-cost run `library_rules_EVT_FLAT_2026-09-29T1105Z.jsonl`, with series in `library_series_EVT_FLAT_.../`
- Corwin-Schultz run `library_rules_EVT_CS_2026-09-29T1110Z.jsonl`, with series in `library_series_EVT_CS_.../`
- board `event_board_EVT_FLAT_2026-09-29T1105Z__2026-09-29T105312Z.json`
- turnover and capacity `event_profile_EVP_2026-09-29T1100Z.json`

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** A negative result, with evidence.

- **76 rules unlocked.** A new point-in-time bridge (IBES targets, recommendations and actuals, plus Form 4)
  unlocked 76 of the 172 library rules that could not run on CRSP. All 76 ran on the survivor-free panel.
  Each ran twice: once at flat costs, once with a per-name Corwin-Schultz spread.
- **0 of 76 meet the decision line declared before the run.** Every rule loses to the market in 2009-2016
  net of spreads.
- **Under the optimistic flat costs, 8 rules clear every leg except the deflated Sharpe.** The best DSR is
  0.18 at the full count, and 0.76 even at a count of only today's 152 cells.
- **What is real is relative, not absolute.** Analyst revision flow beats its matched twin in design,
  validation and the 2017-2024 window alike. `net_raises` is +0.41 / +0.27 / +0.65%/mo, and 9 of 14
  revision-flow rules are positive in validation. It does not beat the market once the twin's own drag
  and realistic costs are counted.
- **Insider buying (Form 4, 2006-2024) is nothing.** 3 of 15 rules are positive against the twin in
  validation, below the rate chance gives.

| item | value |
|---|---|
| best historical net strategy vs the market | unchanged. No rule here beats the market in 2009-2016 net of any cost scheme at t >= 2. |
| rules run on CRSP | **140 (earlier today) + 76 (this note) = 216 of 312**. The remaining 96 need lead/chase, skill, first-mover, short interest, 8-K items, 13F, SEC-facts derivations or news: not built. |
| rules surviving the declared line | **0 of 76** (Corwin-Schultz variant). Flat variant: 0 (8 pass everything but DSR). |
| deflation count used | **n = 42,378**: the reviewer's 42,216 (1,296 cells, 2 blends and the 40,920 four-of-33 blend space) + 10 follow-up cells + 152 cells here (76 rules x 2 cost schemes). The reviewer's 60,000 random draws are a null, not a search, and are not counted. |
| independent selector count | unchanged. |
| farm candidates tested / promoted | 76 tested, 0 promoted, 0 registered. |
| best forward paper strategy | unchanged; nothing matures before 2026-10-26. |
| new actionable finding | Revision flow is a **relative** signal, a real ranking among comparable names, not an **absolute** one. This is consistent with ANALYST-IBES-1 (2026-08-11, "revisions real gross, dead net") on a different instrument, a different engine and eleven more years. |
| external execution drag | not measured |
| LLM spend | $0.00 |

## 1. The bridge: `backend/services/crsp_event_bridge.py`

**The timestamp rule, pinned by 13 offline tests (`backend/tests/test_crsp_event_bridge.py`):**

- **IBES rows** are dated by max(`anndats`, `actdats`): the announcement or the day the row entered IBES,
  whichever is later. Never by a fiscal period.
- **Form 4 rows** are dated by the FILING day (`observed_at_utc`, taken as the New York calendar day),
  never by the transaction date.
- **Lag.** Every event is lagged one business day. It counts at decision date d only if the lagged day
  is on or before d: an event on d itself is not used, and an event on d-1 is.
- **Earnings reaction.** The announcement return is the abnormal return over [e-1, e+1] around the
  reaction session e. A timestamp at or after 16:00 moves e to the next day. The return is usable only
  from the business day after e+1.
- **Link.** The IBES ticker -> permno link uses the `ibcrsphist` row active **on the event date**, lowest
  score first. An event outside every link interval is dropped and counted, never mapped forward.
- **Start dates.** Before each source has a full window, its columns are NaN, never 0, so a tiebreak
  cannot pose as a signal. These dates were declared from the coverage receipt, before any rule ran:
  - targets: from 1999-09 (first usable target 1999-02-22);
  - recommendations: from 1994-11 (first 1993-11, and every broker's first record reads as an "init");
  - Form 4: from 2006-06 (first usable 2006-01-04).

**Translations from the vendor columns.** The library's column names and windows (90/30/180 days) are
kept.

- `net_raises` counts raises minus lowers, where each IBES 12-month USD target is compared with the same
  broker's previous target on the same permno, if that target is at most 365 days old.
- `n_firms` counts distinct brokers with any target or recommendation event.
- Rating up/down/init comes from `ireccd` (a lower code is an upgrade).
- `target_cv_180` uses each broker's latest target, with at least 3 brokers.
- The `ins_*` columns follow the vendor's own event types, from `insider_events_v1` (2006-2024 linked to
  permno).
- Earnings dates come from IBES actuals: quarterly EPS, the first announcement per period, within 120
  days of the period end. Late restatement rows are dropped.

**Not built tonight:** lead/chase, analyst skill and first-mover columns (the 63-session resolution logic),
short interest, 8-K items and 13F.

### Coverage: names per month (mean within the year)

| year | revision flow | ratings | target CV (>=3 brokers) | insider (Form 4) | earnings (`ear_last`) |
|---|---:|---:|---:|---:|---:|
| 1991 | - | - | - | - | 3,492 |
| 1995 | (recs only) | 3,567 | - | - | 4,651 |
| 1999 | 4,192 | 4,111 | 998 | - | 5,312 |
| 2002 | 3,481 | 3,352 | 1,620 | - | 4,314 |
| 2006 | 3,583 | 3,404 | 1,948 | 2,939 | 4,361 |
| 2008 | 3,464 | 3,282 | 1,994 | 3,251 | 4,158 |
| 2012 | 3,087 | 2,874 | 2,027 | 2,685 | 3,355 |
| 2016 | 3,099 | 2,730 | 2,111 | 2,560 | 3,318 |
| 2020 | 3,036 | 2,686 | 2,160 | 2,452 | 3,091 |
| 2024 | 3,294 | 2,625 | 2,175 | 2,508 | 3,302 |

The full by-year series is in the bridge receipt.

- Link rates: targets 80.1% (1,804,423 of 2,252,609), recommendations 78.0%, actuals 65.5%.
- 587,841 earnings events, 587,675 of them priced.
- Target signs: 51% raises, 37% lowers, 12% unchanged or re-initiated.
- Revision-flow columns before 1999-09 are NaN on the panel. The raw coverage above counts
  recommendation-only names from 1993.

## 2. What was run, and the rule declared before it

**The engine is `library_on_crsp.part_run`, unchanged.** It uses the rule's own k, costs on, the 21-draw
matched twin (size band x vol_63 x 12-1 tercile, two seed sets), and the three quarterly offsets for
`disp_short_avoid`. The only change is that the panel loader is wrapped to merge the bridge columns.

**Two cost schemes:**

1. **Flat.** The engine's 2026 band schedule. This is optimistic before 2001.
2. **Flat plus Corwin-Schultz.** The co03 follow-up's per-name, per-month high-low spread on top of flat,
   charged as a full round trip every month to book and twin alike. This is an upper bound: the rules
   here turn over 44-95% a month, not 100%, and the estimator's volatility leak inflates it.

**The split, declared before any rule ran (hold month):**

- design: 1991-2008, but effectively 1999-2008 for analyst flow and 2006-2008 for insider;
- validate: 2009-2016, read once;
- holdout: 2017-2024.

**Honesty note on the holdout.** 2017-2024 is not virgin for these rules. The library's rules were
written on the vendor panel in 2016-2026, which uses a different instrument (yfinance) but the same
calendar. **The honest out-of-sample window for these rule designs is 2009-2016** (and 1999-2008). The
2017-2024 column is description.

**Decision line (in the script's docstring before the run).** A rule SURVIVES iff, on the Corwin-Schultz
variant, all four hold:

1. rule - twin > 0 in both design and validate;
2. rule - market > 0 in both design and validate;
3. rule - twin t >= 2 over 1991-2016;
4. DSR(rule - twin, 1991-2016) >= 0.95 at the full count.

Only a survivor's holdout is read as a decision.

## 3. Results

**Failure reasons, on the Corwin-Schultz variant (a rule can fail several):**

| reason | rules |
|---|---:|
| rule - market <= 0 in validate | **76** |
| DSR < 0.95 | **76** |
| rule - twin t < 2 over 1991-2016 | 68 |
| rule - market <= 0 in design | 65 |
| rule - twin <= 0 in validate | 39 |
| rule - twin <= 0 in design | 19 |

**The leaders.** All figures are %/mo, keyed on the hold month, with the t on 3-month blocks.

| rule | vs twin: design / validate / 2017-24 | twin t 91-16 (MDE) | vs market 2009-16: flat / CS / turnover-scaled CS | turnover | median pick ADV 2010s | DSR @42,378 (@152) |
|---|---|---|---|---:|---:|---|
| `ear_flow` | +1.29 / +0.67 / +0.29 | 3.9 (0.73) | +0.51 (t 1.3) / -0.41 / +0.07 | 48% | $64M | 0.18 (0.76) |
| `mom_flow_trend` | +1.01 / +0.30 / +0.65 | 2.8 (0.67) | +0.12 / -0.60 / -0.32 | 61% | $100M | 0.09 (0.63) |
| `net_raises_trend` | +0.50 / +0.23 / +0.54 | 2.6 (0.40) | -0.06 / -0.58 / -0.38 | 62% | $216M | 0.03 (0.35) |
| `flow_acceleration` | +0.74 / +0.50 / +0.10 | 2.5 (0.70) | +0.39 / -0.39 / -0.35 | 95% | $149M | 0.07 |
| `flow_in_winners` | +0.47 / +0.37 / +0.40 | 2.2 (0.55) | +0.36 (t 1.4) / -0.34 / +0.05 | 44% | $210M | 0.02 |
| `upgrades_net_90` | +0.53 / +0.09 / +0.45 | 2.0 (0.52) | +0.16 / -0.71 / -0.38 | 62% | $86M | 0.02 |
| `net_raises` | +0.41 / +0.27 / +0.65 | 1.8 (0.55) | +0.14 (t 0.6) / -0.58 / -0.17 | 44% | $213M | 0.005 (0.14) |
| `net_raises_secrel` | +0.26 / +0.34 / +0.26 | 1.9 (0.44) | +0.27 (t 1.4) / -0.40 / -0.07 | 50% | $182M | 0.008 |

- "Turnover-scaled CS" is flat + (CS - flat) x turnover: a middle estimate between the two schemes.
- The sd of the `net_raises` gap is 3.4%/mo. Its LOO-worst is +0.37%/mo (dropping 2000), and 17 of
  26 years are positive.

**The twin is a drag on its own.**

- For `net_raises`, twin - market in 2009-2016 is -0.15%/mo flat and **-0.85 (t -3.8) with spreads**.
- The rule's +0.27 over the twin is real relative information. It sits on top of a comparison portfolio
  that loses to the value-weighted market.
- This is the reviewer's lesson ("beats its twin is a weaker claim than it sounds"), measured again here.

**The families (Corwin-Schultz, rule - twin > 0 in validate):**

| family | positive in validate |
|---|---|
| revision_flow | 9 of 14 |
| sector_relative (net_raises-based) | 3 of 3 |
| weighted | 2 of 2 |
| analyst_rating | 4 of 5 |
| earnings_event | 7 of 12 |
| insider | **3 of 15** |
| analyst_dispersion | 0 of 4 |
| all 76 | 37 |

The all-76 count of 37 is chance level. Against the market in validate: **0 of 76** with spreads, and 37
of 76 at flat costs.

**Verdicts, in the project's vocabulary:**

- **Analyst revision flow (`net_raises` and relatives) against the twin:** CANNOT_DISTINGUISH at honest
  multiplicity. The sign is consistent across three eras and two instruments.
  - As a capital idea: **DEPRIORITIZED**. It does not beat the market out of sample net of realistic
    costs.
  - The mechanism is **not rejected**. It is a ranking signal that needs a better base portfolio, not a
    book of its own.
- **Earnings-announcement drift (`ear_*`):** decays. `ear_drift` is +0.49 / +0.43 / -0.47 against the
  twin, and `ear_drift_large` is +1.32 / -0.37 / -0.14. The classical PEAD shape is present pre-2009 and
  gone after. DEPRIORITIZED.
- **`ear_flow` (earnings reaction + revision flow):** the best single rule.
  - Twin t 3.9 over 1991-2016, holding $30-150M/day names.
  - Against the market in validate it is +0.51 at flat costs (t 1.3), +0.07 turnover-scaled and -0.41 at
    full CS. DSR 0.18.
  - CANNOT_DISTINGUISH; the leading lead for a combined test (below).
- **Insider buying (Form 4 on CRSP, 2006-2024):** FAILED_VARIANT for all 15 library insider rules as
  specified. This closes these implementations, not the Cohen-Malloy-Pomorski mechanism. The vendor's
  `insider_open_market_buy` type excludes the opportunistic/routine-classified buys, and the design
  window is 2.5 years.
- **Target dispersion, initiations, "no downgrades" momentum filters:** FAILED_VARIANT or CANNOT_DISTINGUISH,
  about zero.

## 4. ANALYST-SKILL-1

It **was run on 2026-09-26**, as registered, on the registered instrument (`tr_ibes.ptgdetu`) with the
prereg's hash checked.

- The registered rule's word was **ADOPT**: ΔIC +0.00084, paired t 2.52, 71 months.
- The effect is about 1/12 of the declared size, and the mechanism is attenuation of an anti-signal
  consensus.
- Verdict: `docs/ANALYST_SKILL_1_VERDICT_2026-09-26.md`; receipt
  `backend/data/optimus/analyst/analyst_skill_1_receipt.json`.

The brief's "registered 2026-08-31 and never run" is out of date. **It was not re-run under its name
here**, and no substitute test carries its name. The library's `skill_*` rules remain un-run on CRSP:
their skill column is not in this bridge.

## 5. Kill rule and registration

**Not applicable: nothing survived, so no forward contract was registered.**

If the owner wants `ear_flow` as a free shadow anyway, its kill rule has to be sized from the gap's
measured volatility.

- `ear_flow`'s rule - twin gap has a monthly sd of **4.4%** (`net_raises`: 3.4%). Over 126 sessions that
  is about 10.9%.
- A kill at -1.645 of that sd sits at about **-17.9%** over six months.
  - Its false-kill rate under zero edge is 5% by construction.
  - Under a true +0.5%/mo edge, P(kill) is about 3%.
  - It reaches 50% power only against a true gap of about -3%/mo.
- So a six-month shadow can catch a disaster and nothing else.
- This is the reviewer's point in section 6: the idiosyncratic-only convention would have put the line
  near -5% and false-killed about 20% of the time.

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS.**

- **The bridge.** 76 more library rules now run on 34 survivor-free years in about 4.5 minutes per cost
  scheme. Every event is timestamped by announcement/activation or filing date, lagged one business day,
  and linked by the event-date permno. The tests pin each part.
- **Analyst revision flow as a RELATIVE ranking.**
  - Rule - twin is positive in design, validation and 2017-2024 across the `net_raises` family.
  - It is concentrated in liquid names ($100-500M/day median pick), turns over at 44%, and capacity is
    not the constraint.
  - It agrees with ANALYST-IBES-1's "revisions are real gross" on a different engine.
- **Pre-declaring the split and the decision line.** It made "8 rules look great at flat costs" a
  non-event instead of a book.

**WHAT DOES NOT.**

- **Any analyst, insider or earnings rule as a stand-alone book against the market.**
  - 0 of 76 are positive against the market in 2009-2016 with spreads.
  - At flat costs, none is at t >= 2 there.
  - The best DSR at the honest count is 0.18.
- **Insider buying** as the library defines it: 3 of 15 are positive in validation.
- **Post-2009 PEAD**: `ear_drift` and `ear_fresh` are negative in 2017-2024.
- **The matched twin as the only benchmark.** Twin - market is -0.85%/mo (t -3.8) with spreads in
  2009-2016.

**HIGHEST-EV EXPERIMENT.** Use revision flow as an **overlay on a base that already tracks the market**,
not as a book.

- **The test.** Take a large-cap, market-like base (for example the top 500 by dollar volume,
  equal- or cap-weighted) and tilt it by `net_raises` / `ear_flow`.
- **Pre-declare** design 1999-2008 and validate 2009-2016, against the market only, with
  turnover-scaled Corwin-Schultz costs, and count this note's 42,378 plus the new cells.
- **Why it ranks first.** The one consistent thing measured tonight is relative information inside
  comparable names. The book construction, not the signal, is what hands it back to the market (the twin
  drag).
- **Cost and odds.** About 2 hours, $0. P(changes the roadmap) is moderate: a positive result would be the
  first OOS market-relative edge from the project's own information type.
- **Second, cheaper (about 1 hour):** build the lead/chase and first-mover columns into this bridge. That
  is 12 more rules, and the vendor board's only other ALPHA_DETECTED family.

## CONTINUE FROM HERE

Everything is computed and in receipts. The parquet files are local. Nothing is committed (brief).
Reproduce:

```bash
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_crsp_event_bridge.py backend/tests/test_analyst_insider_on_crsp.py -q
python -m scripts.analyst_insider_on_crsp --part bridge --run-id <new id>                       # ~65 s
python -m scripts.analyst_insider_on_crsp --part run --bridge-run EB_2026-09-29T1055Z --run-id <id>        # flat, ~4.5 min
python -m scripts.analyst_insider_on_crsp --part run --bridge-run EB_2026-09-29T1055Z --run-id <id> --cs   # spreads, ~4.5 min
python -m scripts.analyst_insider_on_crsp --part board --flat-run EVT_FLAT_2026-09-29T1105Z --cs-run EVT_CS_2026-09-29T1110Z
python -m scripts.analyst_insider_on_crsp --part profile --bridge-run EB_2026-09-29T1055Z --rules net_raises,ear_flow --tag <id>
```

Files to commit together:

- `backend/services/crsp_event_bridge.py`
- `scripts/analyst_insider_on_crsp.py`
- the two test files
- this note
- the `event_*` json receipts and the two `library_rules_EVT_*.jsonl`

`crsp_event_bridge` is reached through the script, and `test_signal_reachability` passes (9/9) with no
classification edit.

## Appendix: all 76 rules

The table below is in %/mo, on the Corwin-Schultz variant unless marked flat.

- D is design 1991-2008, V is validate 2009-2016, H is 2017-2024.
- "from" is the first decision month with data.
- The DSR is at n = 42,378.

| rule | family | from | twin D / V / H (CS) | twin t 91-16 (MDE) | market D / V / H (CS) | market V (flat) | DSR |
|---|---|---|---|---|---|---|---:|
| `ear_flow` | earnings_event | 1999-09 | +1.29 / +0.67 / +0.29 | +3.9 (+0.73) | +0.14 / -0.41 / -0.64 | +0.51 | 0.181 |
| `mom_flow_trend` | regime_gated | 1999-09 | +1.01 / +0.30 / +0.65 | +2.8 (+0.67) | +0.99 / -0.60 / -0.69 | +0.12 | 0.088 |
| `net_raises_trend` | regime_gated | 1999-09 | +0.50 / +0.23 / +0.54 | +2.6 (+0.40) | +1.01 / -0.58 / -0.55 | -0.06 | 0.025 |
| `flow_acceleration` | revision_flow | 1999-09 | +0.74 / +0.50 / +0.10 | +2.5 (+0.70) | -0.47 / -0.39 / -0.88 | +0.39 | 0.065 |
| `ear_fresh` | earnings_event | 1991-01 | +0.62 / +0.34 / -0.31 | +2.4 (+0.63) | -1.00 / -0.96 / -2.19 | +0.11 | 0.024 |
| `ear_drift_large` | earnings_event | 1995-07 | +1.32 / -0.37 / -0.14 | +2.2 (+0.86) | -0.49 / -1.12 / -0.84 | -0.30 | 0.048 |
| `flow_in_winners` | flow_momentum | 1999-09 | +0.47 / +0.37 / +0.40 | +2.2 (+0.55) | +0.13 / -0.34 / -0.24 | +0.36 | 0.015 |
| `upgrades_net_90` | analyst_rating | 1994-11 | +0.53 / +0.09 / +0.45 | +2.0 (+0.52) | -0.59 / -0.71 / -0.67 | +0.16 | 0.022 |
| `net_raises_30d` | revision_flow | 1999-09 | +0.64 / +0.04 / +0.11 | +2.0 (+0.51) | +0.03 / -0.73 / -0.66 | +0.01 | 0.013 |
| `eap_lowvol` | earnings_event | 1991-01 | +0.43 / -0.12 / -0.30 | +1.9 (+0.38) | -0.25 / -0.72 / -1.14 | -0.32 | 0.011 |
| `ear_drift` | earnings_event | 1991-01 | +0.49 / +0.43 / -0.47 | +1.9 (+0.70) | -1.04 / -0.59 / -1.81 | +0.64 | 0.010 |
| `net_raises_secrel` | sector_relative | 1999-09 | +0.26 / +0.34 / +0.26 | +1.9 (+0.44) | -0.08 / -0.40 / -0.42 | +0.27 | 0.008 |
| `net_raises` | revision_flow | 1999-09 | +0.41 / +0.27 / +0.65 | +1.8 (+0.55) | +0.10 / -0.58 / -0.14 | +0.14 | 0.005 |
| `ear_mom` | earnings_event | 1991-01 | +0.73 / -0.07 / -0.04 | +1.7 (+0.77) | -0.16 / -1.32 / -1.31 | -0.16 | 0.003 |
| `eap_raises` | earnings_event | 1999-09 | +0.68 / +0.06 / +0.21 | +1.7 (+0.66) | -0.03 / -0.64 / -0.37 | +0.09 | 0.005 |
| `mom_flow_small` | combination | 1999-09 | +0.52 / +0.68 / +0.43 | +1.6 (+1.07) | -0.09 / -0.56 / -1.22 | +0.46 | 0.004 |
| `flow_rule` | revision_flow | 1999-09 | +0.37 / +0.17 / +0.48 | +1.5 (+0.52) | -0.02 / -0.56 / -0.10 | +0.14 | 0.002 |
| `mom_no_downgrades_large` | revision_flow | 1999-09 | +1.08 / -0.12 / +0.58 | +1.5 (+0.98) | -0.33 / -0.96 / +0.07 | -0.17 | 0.005 |
| `flow_rule_large` | revision_flow | 1999-09 | +0.44 / +0.14 / +0.60 | +1.5 (+0.57) | -0.34 / -0.55 / -0.09 | +0.11 | 0.002 |
| `net_raises_ivw` | weighted | 1999-09 | +0.36 / +0.16 / +0.36 | +1.4 (+0.54) | +0.04 / -0.53 / -0.30 | +0.14 | 0.002 |
| `net_raises_small` | revision_flow | 1999-09 | +0.43 / +0.20 / +0.32 | +1.3 (+0.68) | -0.01 / -0.75 / -0.99 | +0.12 | 0.002 |
| `div_quality_lowvol_insider` | diversified_combo | 2006-06 | +0.65 / +0.13 / +0.07 | +1.3 (+0.54) | +0.04 / -0.33 / -0.87 | +0.24 | 0.003 |
| `mom_flow` | combination | 1999-09 | +0.61 / +0.27 / +0.73 | +1.3 (+0.99) | -0.21 / -0.77 / -0.03 | +0.16 | 0.003 |
| `mom_flow_secrel` | sector_relative | 1999-09 | +0.61 / +0.02 / +0.14 | +1.2 (+0.75) | -0.01 / -0.97 / -0.58 | -0.10 | 0.003 |
| `target_change` | revision_flow | 1999-09 | +0.97 / -0.11 / +1.08 | +1.2 (+1.09) | -0.33 / -1.11 / -0.72 | +0.16 | 0.001 |
| `upgrades_net_large` | analyst_rating | 1995-07 | +0.37 / +0.05 / +0.02 | +1.2 (+0.60) | -0.93 / -0.59 / -0.82 | +0.15 | 0.002 |
| `net_raises_large` | revision_flow | 1999-09 | +0.27 / +0.17 / +0.46 | +1.1 (+0.59) | -0.49 / -0.48 / -0.23 | +0.18 | 0.001 |
| `init_mom` | analyst_rating | 1994-11 | +0.40 / +0.04 / +0.21 | +1.0 (+0.74) | -0.66 / -1.03 / -0.80 | -0.10 | 0.001 |
| `target_change_lowvol` | flow_momentum | 1999-09 | +0.12 / +0.19 / +0.12 | +1.0 (+0.42) | -0.05 / -0.57 / -0.80 | -0.04 | 0.001 |
| `runup_exit_before_large` | earnings_event | 1999-11 | +0.18 / +0.20 / +0.23 | +1.0 (+0.53) | -1.09 / -0.65 / -0.67 | +0.00 | 0.001 |
| `mom_flow_ivw` | weighted | 1999-09 | +0.61 / +0.01 / +0.64 | +1.0 (+0.94) | -0.11 / -0.86 / -0.05 | +0.01 | 0.001 |
| `eap_mom` | earnings_event | 1991-01 | +0.43 / +0.02 / +0.38 | +1.0 (+0.87) | -0.68 / -1.12 / -0.88 | +0.01 | 0.001 |
| `insider_before_print` | earnings_event | 2006-06 | -0.00 / +0.38 / +0.84 | +1.0 (+0.83) | -1.91 / -0.45 / -1.07 | +0.55 | 0.001 |
| `insider_then_raise` | insider | 2006-06 | +0.88 / +0.10 / -0.25 | +1.0 (+0.82) | -1.16 / -0.71 / -1.58 | +0.18 | 0.001 |
| `insider_net_ratio` | insider | 2006-06 | -0.31 / +0.45 / +0.41 | +0.9 (+0.80) | -1.90 / -0.61 / -1.43 | +0.36 | 0.000 |
| `flow_accel_mom` | flow_momentum | 1999-09 | +0.56 / -0.07 / +0.17 | +0.9 (+0.86) | -0.06 / -1.17 / -0.96 | -0.22 | 0.000 |
| `low_target_dispersion` | analyst_dispersion | 1999-09 | +0.33 / -0.09 / +0.36 | +0.8 (+0.47) | -0.23 / -1.10 / -0.81 | -0.45 | 0.000 |
| `runup_exit_before` | earnings_event | 1999-09 | +0.36 / -0.03 / +0.11 | +0.7 (+0.65) | -0.67 / -1.01 / -1.31 | -0.19 | 0.000 |
| `div_agree_quality_lowvol` | diversified_combo | 1999-09 | +0.06 / +0.16 / +0.04 | +0.7 (+0.40) | -0.11 / -0.46 / -0.65 | +0.01 | 0.000 |
| `net_raises_180d` | revision_flow | 1999-09 | +0.10 / +0.22 / +0.61 | +0.7 (+0.62) | -0.14 / -0.63 / -0.07 | +0.07 | 0.000 |
| `mom_in_raised` | flow_momentum | 1999-09 | +0.57 / -0.06 / +0.59 | +0.7 (+1.16) | -0.51 / -1.14 / -0.62 | +0.08 | 0.000 |
| `flow_lowvol` | combination | 1999-09 | +0.18 / -0.04 / -0.02 | +0.5 (+0.42) | -0.09 / -0.69 / -0.70 | -0.25 | 0.000 |
| `mom_no_insider_selling` | insider | 2006-06 | -0.59 / +0.39 / +0.16 | +0.4 (+0.99) | -2.86 / -0.80 / -1.06 | +0.40 | 0.000 |
| `flow_rule_q` | revision_flow | 1999-11 | +0.28 / -0.18 / +0.48 | +0.4 (+0.43) | -0.26 / -0.81 / -0.13 | -0.10 | 0.000 |
| `gp_flow` | combination | 1999-09 | +0.56 / -0.47 / +0.07 | +0.4 (+0.65) | +0.08 / -1.21 / -0.52 | -0.46 | 0.000 |
| `low_target_dispersion_large` | analyst_dispersion | 1999-09 | +0.10 / -0.07 / -0.11 | +0.2 (+0.43) | -0.48 / -0.71 / -0.77 | -0.25 | 0.000 |
| `cluster_unconfirmed` | lead_chase | 1999-09 | -0.24 / +0.31 / -0.17 | +0.1 (+0.65) | -1.84 / -0.57 / -1.28 | +0.29 | 0.000 |
| `insider_buyers_large` | insider | 2006-06 | +0.35 / -0.09 / +0.76 | +0.1 (+0.61) | -1.74 / -0.58 / -0.11 | +0.15 | 0.000 |
| `n_firms_acting` | revision_flow | 1999-09 | -0.01 / +0.03 / +0.30 | +0.0 (+0.75) | -1.43 / -0.72 / -0.44 | +0.07 | 0.000 |
| `insider_secrel` | sector_relative | 2006-06 | -0.21 / +0.07 / +0.22 | +0.0 (+0.71) | -1.72 / -0.48 / -1.21 | +0.48 | 0.000 |
| `insider_officer` | insider | 2006-06 | +0.79 / -0.26 / -0.16 | -0.0 (+0.90) | -0.95 / -1.08 / -1.86 | -0.08 | 0.000 |
| `insider_in_calm` | regime_gated | 2006-06 | +0.02 / -0.01 / +0.04 | -0.0 (+0.41) | +1.08 / -1.15 / -1.75 | -0.86 | 0.000 |
| `mom_no_rating_downgrade` | analyst_rating | 1994-11 | +0.40 / -0.76 / +0.03 | -0.0 (+1.27) | -0.66 / -1.77 / -1.21 | -0.48 | 0.000 |
| `mom_no_downgrades_trend` | regime_gated | 1999-09 | +0.33 / -0.49 / +0.35 | -0.1 (+1.03) | +0.29 / -1.39 / -1.53 | -0.38 | 0.000 |
| `low_dispersion_mom` | analyst_dispersion | 1999-09 | +0.11 / -0.20 / +0.12 | -0.2 (+0.55) | -0.41 / -1.29 / -1.17 | -0.46 | 0.000 |
| `insider_opportunistic` | insider | 2006-06 | -0.19 / -0.03 / +0.13 | -0.2 (+0.78) | -1.77 / -0.56 / -1.53 | +0.42 | 0.000 |
| `insider_flow` | insider | 2006-06 | +0.87 / -0.39 / +0.58 | -0.4 (+0.66) | -0.07 / -1.11 / -0.48 | -0.29 | 0.000 |
| `raises_in_losers` | flow_momentum | 1999-09 | -0.00 / -0.17 / +0.28 | -0.4 (+0.60) | -0.25 / -0.99 / -0.37 | -0.24 | 0.000 |
| `raise_price_gap` | lead_chase | 1999-09 | -0.02 / -0.20 / +0.18 | -0.4 (+0.70) | -0.99 / -1.20 / -1.18 | -0.23 | 0.000 |
| `insider_cluster_small` | insider | 2006-06 | -0.17 / -0.11 / +0.00 | -0.4 (+0.81) | -1.96 / -0.91 / -2.09 | +0.23 | 0.000 |
| `disp_short_avoid` | analyst_dispersion | 1991-03 | +0.26 / -1.14 / -0.09 | -0.5 (+0.97) | -0.73 / -2.25 / -1.38 | -0.97 | 0.000 |
| `eap_avoid_mom` | earnings_event | 1991-01 | +0.23 / -1.05 / -0.31 | -0.5 (+0.90) | -0.76 / -2.27 / -1.67 | -1.04 | 0.000 |
| `mom_with_insider_buying` | insider | 2008-04 | +1.37 / -0.27 / -0.08 | -0.5 (+0.75) | -0.77 / -1.25 / -1.43 | -0.28 | 0.000 |
| `mom_no_downgrades` | revision_flow | 1999-09 | +0.42 / -1.05 / +0.48 | -0.6 (+1.20) | -0.57 / -2.08 / -0.75 | -0.78 | 0.000 |
| `attention_reversal` | flow_momentum | 1999-09 | -0.26 / -0.28 / +0.14 | -0.8 (+0.98) | -2.31 / -1.32 / -1.35 | -0.25 | 0.000 |
| `mom_no_downgrades_small` | revision_flow | 1999-09 | -0.18 / -0.49 / +0.65 | -0.8 (+1.13) | -1.08 / -1.64 / -1.18 | -0.35 | 0.000 |
| `initiations_90` | analyst_rating | 1994-11 | -0.38 / +0.22 / -0.23 | -0.8 (+0.57) | -1.72 / -0.87 / -1.06 | -0.06 | 0.000 |
| `div_mom_insider_flow` | diversified_combo | 2006-06 | +0.27 / -0.30 / +0.65 | -0.8 (+0.54) | -1.63 / -1.34 / -0.33 | -0.44 | 0.000 |
| `insider_buyers` | insider | 2006-06 | +0.62 / -0.64 / +0.22 | -0.8 (+1.12) | -1.36 / -1.38 / -1.52 | -0.28 | 0.000 |
| `insider_opp_mom` | insider | 2006-06 | -0.62 / -0.17 / -0.33 | -0.9 (+0.83) | -2.16 / -1.20 / -1.60 | -0.22 | 0.000 |
| `insider_cluster_value` | insider | 2006-06 | -0.18 / -0.40 / -0.30 | -1.1 (+0.87) | -2.19 / -1.16 / -2.17 | -0.04 | 0.000 |
| `div_insider_reversal` | diversified_combo | 2006-06 | -1.01 / -0.30 / -0.14 | -1.2 (+1.14) | -3.63 / -1.30 / -1.96 | -0.24 | 0.000 |
| `insider_buy_dip` | insider | 2006-06 | -0.47 / -0.90 / +0.37 | -1.3 (+1.68) | -3.00 / -1.77 / -1.97 | -0.39 | 0.000 |
| `flow_hi52` | flow_momentum | 1999-09 | -0.53 / -0.15 / +0.08 | -1.5 (+0.65) | -0.90 / -1.07 / -0.92 | -0.42 | 0.000 |
| `insider_mom` | insider | 2006-06 | -0.05 / -0.63 / +0.95 | -1.6 (+0.88) | -1.85 / -1.79 / -0.33 | -0.68 | 0.000 |
| `insider_unconfirmed` | insider | 2006-06 | +0.23 / -0.89 / -0.09 | -1.8 (+0.98) | -1.78 / -1.78 / -1.93 | -0.69 | 0.000 |
