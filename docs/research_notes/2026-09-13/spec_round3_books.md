# Spec: five builder-ready books from round-3 strategy ideas (2026-09-13)

Scope: `docs/research_notes/2026-09-13/research_strategy_ideas_round3.md`
ideas #1-#5, turned into constructions a builder can run tomorrow against
data verified ON DISK by direct pandas reads (schemas below are measured, not
assumed). Templates: `docs/research_notes/2026-09-12/spec_first_books.md`
(chunk 5 house style) and `docs/TRIALS/TRIAL-DRAFT-F-calendar-seasonality-v0.md`
(MDE arithmetic, decision-rule shape, frozen-parameters shape). Engine read in
full: `scripts/night_first_books_replay.py` (`load_monthly_panel`, `eligible`,
`run_monthly`, `pool_filter`) and `scripts/night_books_efg_replay.py` (how a
new book wraps that engine with `pool_filter`). Every book here is
`PRODUCT_EXPERIMENT` — no significance gate to *build*, but each carries a
`pre-register-trial` file before its first read, per CLAUDE.md's three
licences, and each is a NEW family (its own Holm block), never folded into
`NIGHT_JOB_BOOKS_2026_09_13` (E/F/G/C_v1), whose four-primary budget is spent.

**Ranking (evidence × buildability), most to least buildable-now:**

1. **Book H — option-grant opportunistic timing** (idea #2). Zero pull: the
   raw code exists on disk, unread, in a table already built for a different
   purpose.
2. **Book I — buyback-vs-insider-selling divergence** (idea #4). Zero pull:
   two tables already on disk, never joined this way.
3. **Book J — the survivor combination** (idea #5, this task's redefinition:
   F@$10M + C_v1@$3M + the DSR-surviving G3 lineage). Zero pull, but the
   hardest plumbing (three frozen contracts, one combined ledger).
4. **Book K — AI-washing / talk-vs-walk language** (idea #1). Needs a FREE
   PULL (EDGAR full-text search) — no 10-K/10-Q body text is on disk anywhere
   in this repo (verified below); `BLOCKED_ON_DATA` until N-A-shaped collector
   lands.
5. **Book L — universe-wide hiring-rate factor** (idea #3). Needs a FREE PULL
   (Greenhouse/Lever/Ashby) at a scale N-G's three-ticker prereg never
   required; `BLOCKED_ON_DATA` until `scripts/hiring_pull.py` exists. Ranked
   last only on build cost — the published evidence (Kuehn-Simutin-Wang,
   Kothari-O'Doherty) is the strongest single citation in this batch.

**Opus builds H and I first.** Both are `k=30`, both floor pairs, both twins,
zero collectors, and both close a registry gap CLAUDE.md itself names
("management motivation... no research exists yet"). J is next (it only
assembles receipts that already exist). K and L are Sonnet data-acquisition
tasks (chunk 4-shaped) before any Opus replay job is worth writing.

---

## 0. Cross-cutting notes (read once, applies to H/I/J)

**Engine.** All three data-ready books (H, I, J's legs) replay through
`night_first_books_replay.run_monthly(panel, select, k=, seed=, label=,
floor_usd=, pool_filter=)`, copying `scripts/night_books_efg_replay.py`'s
shape exactly: one file per book family, `pool_filter` narrows the eligible
band to names that carry the required characteristic BEFORE the book or its
twin is drawn (H needs a grant that quarter; I needs both a buyback flag and
Form-4 coverage; J's F/C_v1 legs already ran and only need their own receipts
re-read). `load_monthly_panel` supplies `permno, ym, ret_m, price, dv,
turnover_m` from `crsp_dsf_<year>.parquet` (columns `permno, date, ret, prc,
vol, shrout`, verified present 1990-2024); `eligible()` applies `MIN_PRICE`
and `floor_usd` (the $3M primary, re-called at $10M secondary) together, so
book and twin always share a floor. **Both floors, one job, twin re-drawn at
each** — Book C's 2026-09-13 lesson ("the registered construction is a test
input, and the receipt must print it") applies to every book below: every
receipt prints its `registered_construction` block and a
`honours_the_registration` boolean.

**k, cost, twin.** k = 30 (H, I; matches E/F/G/A/C), monthly rebalance unless
stated, `_turnover_matched_draw` twin (uniform draw from the SAME `pool_filter`
band, turnover-matched to the book), flat 25 bps per side
(`cost_curve: flat_25bps_pending_5c`), Newey-West lag-2 t on the monthly
block-difference series, `by_era` reported never deciding.

**MDE.** Same panel, same k=30 as Books E/F/G/C: median cross-sectional
monthly return sd 0.167186 → book sd 0.030524 → book-minus-twin sd (×√2)
**0.043167**, 360 nominal monthly blocks → **MDE 0.637%/month** at 80% power,
α 0.05, two-sided; deflated by the measured lag-1 rho (0.1268 on this panel at
k=30) to **0.724%/month**. Every book below reuses these two numbers as its
power baseline and re-measures its own realised block series' rho before the
decision (TRIAL-DRAFT-F §4's rule), printing both.

**Decision-rule skeleton, shared by H/I (fill in the book-specific
falsifiers)**, copied from TRIAL-DRAFT-F §5:
- `PRODUCT_PROMISING`: $3M net block-mean ≥ declared effect at NW t ≥ 2.0,
  AND both falsifiers pass, AND positive sign in ≥ 3 of 4 eras, AND the $10M
  cell is also positive.
- `FAILED_VARIANT`: (i) the $3M net block-mean ≤ 0, whatever the falsifiers
  did — **a primary ≤ 0 closes the book**, the TRIAL-DRAFT-C Amendment-1
  clause, carried into every new book from the start rather than added after
  a read; (ii) the book's own placebo pays as well as the book.
- `CONDITIONAL`: clears the primary but fails era-stability, floor, or lands
  NW t in [1.0, 2.0).
- `CANNOT_DETERMINE`: a falsifier that could not be computed is not a
  falsifier that passed, stated in those words.
- **Contamination clause**: if the covered band (names passing `pool_filter`)
  falls below 0.10 of that year's eligible names, or below 3×k in the median
  month of that year, the year is EXCLUDED and the exclusion is reported
  before the number.
- **Crash override**: a decision within 6 months of an SPY trough ≥ −20% is
  deferred to ≥ 6 months past the trough.
- **Never resurrects**: none of H/I/J touch the closed reaction lane (RW2),
  PEAD, or the CMP open-market-buy trials (`TRIAL-INSIDER-IC`,
  `TRIAL-CMP-INSIDER-IC`) — H and I are new mechanisms on the SAME raw table,
  named as such in each corpse check.

---

## 1. Book H — executive option-grant opportunistic timing

### Mechanism, precursor
Daines et al.: scheduled option grants create an incentive to depress the
stock price around the known grant date (or to time the grant at a trough),
rather than to backdate it. The **precursor observable beforehand** (invariant
2): a filer's OWN history of pre-grant-trough / post-grant-pop patterns,
measured on strictly prior grants, before the grant being scored. This is the
"governance-quality proxy" framing from the round-3 note — an insider/firm
that has shown this pattern before is scored on it going forward, never on
the grant currently being priced.

### Data — measured on disk, 2026-09-13
`backend/data/optimus/sec_insider/parsed/<YYYYqN>.parquet`, **82 files,
2006q1..2026q2**, one row per non-derivative-or-derivative Form-4 transaction
line. Verified columns (42 total; the load-bearing ones):
`issuer_cik, issuer_name, symbol, permno, permno_link_method, owner_cik,
owner_name, is_director, is_officer, table, security_title, trans_code,
trans_class, acquired_disposed, shares, price_per_share, dollar_value,
plan_10b5_1, plan_10b5_1_source, filing_date, observed_at_utc,
observed_at_basis`.

**Confirmed on 2015q1 (170,696 rows) as a receipt, not an assumption:**
`trans_code == 'A'` → `trans_class == 'GRANT_AWARD'`, **48,182 rows**, split
`table`: NONDERIV 24,755 / DERIV 23,427; `security_title` top values `Common
Stock` (16,225), `Restricted Stock Units` (3,025), `Stock Option (Right to
Buy)` (1,245 + 1,178 case variants), `Employee Stock Option (right to buy)`
(892). **This is the code EXCLUDED from `insider_events_v1.parquet`** —
`scripts/sec_insider_bulk_load.py:642-643` filters the distilled events table
to `is_open_market_purchase | is_open_market_sale` only, discarding every
`GRANT_AWARD`, `OPTION_EXERCISE` and `TAX_OR_EXERCISE_WITHHOLDING` row at that
step. **The raw per-quarter parquet is HAVE; the distilled table is not the
right input — read `parsed/*.parquet` directly.** Restrict to `table ==
'DERIV'` for option grants specifically (stock-option awards, per the round-3
idea's "option-grant" framing); `table == 'NONDERIV'` rows are RSU/restricted-
stock grants, a different instrument with no strike and no announcement-pop
literature attached — keep the two tables separate diagnostics, DERIV is
primary.

**PIT rule.** `observed_at_utc = FILING_DATE at 22:00 America/New_York`,
`observed_at_basis = "FILING_DATE_EOD_CONSERVATIVE"` (module docstring,
`sec_insider_bulk.py`); no acceptance timestamp exists in the bulk files, so
the earliest tradable session is the NEXT session's open after
`observed_at_utc`, exactly as the open-market-purchase trials already use.
**Every date used is `filing_date`, never `trans_date`** — the transaction
happens up to two business days before anyone outside the issuer can see it,
and this table's whole PIT defense rests on that gap being honoured.

### Construction
For each (`issuer_cik`, `owner_cik`) pair with ≥ 3 strictly-prior `DERIV`
`GRANT_AWARD` filings before the grant being scored: compute the pre-grant
20-trading-day CRSP return (from `crsp_dsf_<year>.parquet`, `permno` linked via
`insider_events_v1`'s own `permno_link_method` logic — reuse
`sec_insider_bulk.py`'s CRSP-stocknames link, do not re-derive it) and the
post-grant 20-trading-day return, for each prior grant. A filer/insider pair
whose PRIOR grants show (mean pre-grant CAR < 0 AND mean post-grant CAR > 0),
both at the top tercile of that joint statistic across all qualifying pairs
that month, is the "opportunistic-timing" cross-sectional bucket. **The book
selects the ISSUER'S stock**, not the insider — aggregate to
issuer-month if multiple insiders at one issuer qualify (median of their
scores), because the book trades `permno`, not `owner_cik`.

`pool_filter`: names with ≥ 1 `DERIV` `GRANT_AWARD` row with a resolved
`permno` in the trailing 36 months AND ≥ 3 strictly-prior grants for at least
one insider at that issuer (the minimum needed to compute the "history"
Daines' mechanism requires). k = 30, monthly rebalance, hold 1 month (a grant-
timing score is a slow-moving governance characteristic, not an event book —
unlike N1's day-scale insider-buy read).

### Twin
Turnover-matched random draw from the SAME `pool_filter` band (issuers that
HAVE ≥ 3 prior grants but were not selected this month) — the standard
engine twin, not a separate placebo. The coverage-selection concern (grant-
history-rich firms skew larger/older, like the seasonality book's twenty-year-
tape skew) is handled the same way F handles it: the twin is drawn from the
identical covered pool, so the skew is shared.

### Falsifiers (two, both required)
1. **Random-date placebo** (the round-3 note's stated control, and this repo's
   own "verified before believed" habit): recompute the same score using a
   RANDOMLY relabeled grant date 90-180 days off the true grant, same insider,
   same firm. If the placebo score ranks issuers the same way, the "pattern"
   is name-level persistence in the insider's trading pattern generally, not
   grant-timing skill specifically, and the book is `FAILED_VARIANT`.
2. **Routine-vs-opportunistic CMP classifier applied to grants**
   (`backend.services.sec_insider_bulk.classify_routine_opportunistic`,
   already built and pinned by test against `cmp_insider.classify_buy`): split
   the book by whether the SAME insider's grants are CMP-routine (same
   calendar month, 3 straight prior years) or CMP-opportunistic. If routine-
   grant firms show the same pre/post CAR pattern as opportunistic-grant
   firms, the effect is calendar noise (scheduled-grant mechanics), not a
   governance signal, and the "opportunistic" framing is falsified even if the
   pooled book survives — report both legs, the pooled primary is the
   opportunistic-only leg.

### Ruler
**Not found** — the cited literature (Daines et al.; the 2015 *J. Corporate
Finance* 80%-of-grants-timed-on-splits study) is event-study CARs around a
grant date, not a portfolio monthly-spread number. Use the $451,748/grant
economic-magnitude figure only as a sanity check that the selected names'
dollar moves are plausible, never as a return target. Declared effect size:
**0.65%/month** (same conservative choice as Book F, for the same reason — no
mean-spread ruler exists to size against).

### Corpse check
Resurrects nothing: `TRIAL-INSIDER-IC`/`TRIAL-CMP-INSIDER-IC` are `trans_code
== 'P'` only and explicitly exclude grants; Book B (insider clusters,
`FAILED_VARIANT`) is also code `P`. This is the FIRST book on `trans_code ==
'A'` in the repo. Run `python scripts/lint_prereg.py` against the pre-reg file
before any read.

### Replay job shape
`scripts/night_book_h_option_grants.py`, copying
`scripts/night_books_efg_replay.py`'s header block verbatim (WHY THIS JOB
EXISTS / THE SAME ENGINE / WHAT IS NEW IS `pool_filter` / BOTH FLOORS / THE
RECEIPT PRINTS THE CONSTRUCTION), with a `FAMILY` declared at size 1 (H is a
single new primary, not bundled with I unless both are ready the same night —
if bundled, declare the family at 2 before either reads, Holm across both).
New helper needed: `_grant_history(permno-or-owner_cik, asof)` reading only
`parsed/*.parquet` files with `filing_date < asof`, cached per month.

---

## 2. Book I — buyback-vs-insider-selling divergence

### Mechanism, precursor
Corporate buybacks while insiders sell heavily is an agency-conflict signal
(management may be supporting the price against their own private
information); buybacks while insiders hold/buy is bullish confirmation. The
round-3 note's cited 2025 cross-country study (3.7M insider transactions, 34
countries): composite buy/sell measures ≥ 1%/mo equal-weighted, and buyback-
signal quality improves when insider ownership is LOW — i.e. the DIVERGENCE
is the signal, not either leg alone. Precursor: the divergence is knowable
the quarter the buyback is reported AND the sales are filed — both PIT-dated,
neither requires foresight.

### Data — measured on disk, 2026-09-13
- **Buybacks**: `backend/data/optimus/wrds/bulk/comp__funda.parquet`
  (**941,807 rows, 949 columns, `datadate` 1950-06-30 .. 2026-07-31**),
  column **`prstkc`** (Compustat annual, "Purchase of Common and Preferred
  Stock", cash-flow statement) — confirmed present, alongside `prstkcc`,
  `prstkpc`, `tstk`/`tstkc`/`tstkme`/`tstkn`/`tstkp` (treasury-stock levels,
  a second construction if `prstkc` flow is too coarse). Keyed by `gvkey,
  datadate`. **`compustat_fundq.parquet` (the quarterly panel already read by
  E/F/G/A/C) has NO buyback column** (31 columns, verified: `gvkey, datadate,
  rdq, fyearq, fqtr, saleq, revtq, cogsq, xsgaq, oibdpq, ibq, niq, epspxq,
  epsfxq, atq, actq, cheq, rectq, invtq, lctq, ltq, dlttq, dlcq, ceqq, seqq,
  txditcq, oancfy, capxy, dvy, cshoq, prccq` — none is a repurchase field), so
  **this book is annual-frequency on the buyback leg** unless a quarterly
  Compustat pull is added later; state that plainly in the receipt rather than
  quietly switching to `funda`'s annual cadence without saying so.
- **Insider sales**: `backend/data/optimus/sec_insider/parsed/*.parquet`,
  `trans_code == 'S'`, `table == 'NONDERIV'`, `acquired_disposed == 'D'`
  (dispose) — confirmed 29,367 sale rows in the 2015q1 sample alone.
  `dollar_value` and `shares_owned_following` (for the %-of-holdings cut,
  falsifier 1 below) are both present columns.
- **Link**: `backend/data/optimus/wrds/link_ccm.parquet`
  (**33,324 rows**, columns `gvkey, permno, linktype, linkprim, linkdt,
  linkenddt`) joins Compustat `gvkey` to CRSP `permno`; apply the standard
  `linktype in ('LU','LC')` / `linkprim in ('P','C')` / date-range filter (the
  same join E/F/G already use for JKP, and A/C already use for CRSP).

### PIT rule
**Buyback leg**: `rdq` (Compustat's "report date of quarterly earnings", the
closest field to a public-availability date on `funda`/`fundq`) if present for
that fiscal year's filing, else `datadate + 90 calendar days` as the
conservative fallback (10-K filed no later than that for large accelerated
filers) — **state which basis fired, per row, in the receipt**, the same
honesty `sec_insider_bulk.py` applies to its own `observed_at_basis`.
**Insider-sale leg**: `filing_date` at 22:00 ET, exactly Book H's rule.
**The divergence signal forms at the LATER of the two dates** — the book
cannot know both legs until both are public.

### Construction
For each issuer-quarter (or issuer-year on the `funda` cadence): `buyback_flag
= prstkc > 0` (or a dollar-scaled `prstkc / market_cap` continuous version,
reported as a diagnostic); `insider_sell_intensity` = sum of `dollar_value`
for `trans_code == 'S'` filings in the trailing 90 days, scaled by
`shares_owned_following` at the start of the window (a %-of-holdings measure,
per falsifier 1). **Divergence score** = `buyback_flag AND insider_sell_
intensity in the top tercile` (bearish leg, avoid/short) vs `buyback_flag AND
insider_sell_intensity == 0 or bottom tercile` (bullish-confirmation leg,
long). The book LONGS the confirmation leg — that is the direction the round-
3 note's own literature supports (buyback quality improves when insider
ownership stays high / selling stays low), and is the primary; the bearish
leg (buyback + heavy insider selling) is a REPORTED short/avoid diagnostic,
never blended into the same primary metric (mirrors G's high-disp/low-disp
split, which reports both legs and decides on one).

`pool_filter`: names with a resolved `gvkey→permno` link AND a non-null
`prstkc` observation in the trailing 12 months (whether or not it fired) AND
≥ 1 Form-4 filing (any code) in the trailing 12 months — the coverage-parity
requirement, so the twin is drawn from names that COULD have shown either
signal, not from the full universe. k = 30, quarterly rebalance (buyback data
is quarterly/annual-frequency; a monthly rebalance on a quarterly signal is
look-ahead-safe but adds nothing — state the slower cadence explicitly, unlike
E/F/G/H which are monthly).

### Twin
Turnover-matched random draw from the same `pool_filter` band (buyback-
active-or-eligible, Form-4-covered names not selected).

### Falsifiers
1. **Large-sale-only vs small-sale-only split** (the FAJ 2004 finding the
   round-3 note cites: only large %-of-holdings sales carry negative
   information; small sales are diversification noise). Recompute
   `insider_sell_intensity` restricted to sales that are ≥ 10% of
   `shares_owned_following` pre-sale; if the divergence signal is driven
   entirely by SMALL sales, the mechanism is not the one claimed and the book
   is `FAILED_VARIANT` even if the pooled number clears.
2. **10b5-1 plan flag exclusion**: recompute with `plan_10b5_1 == 'YES'` sales
   excluded (pre-scheduled sales carry no signal by construction, per
   `sec_insider_bulk.py`'s own `is_discretionary_open_market_purchase` logic
   applied to the sale side). If excluding scheduled sales KILLS the primary,
   the signal was mechanical scheduling correlation, not discretionary
   information — falsifier fires, book closes. Note the checkbox only exists
   from 2023 Q2 (SEC rule); pre-2023 rows carry `plan_10b5_1_source ==
   'ABSENT'` or `'FOOTNOTE'`, never a silent False, so the pre-2023 exclusion
   rate is reported and may be much lower than post-2023 — this is a KNOWN
   coverage seam, not a bug to paper over.

### Ruler
**≥ 1%/mo** composite alpha (2025, 34-country cross-country study) as the
CEILING prior; haircut to **~0.5%/mo** working declared effect given this
book's narrower single-market, quarterly-cadence, costed construction — still
above the 0.724%/month deflated MDE only marginally, so this book is close to
its own power floor by design; state that rather than picking a number that
clears the bar cosmetically.

### Corpse check
Not the same test as `TRIAL-INSIDER-IC`/`TRIAL-CMP-INSIDER-IC` (buys only,
no buyback join) or Book B (cluster length, no buyback join). First book to
join `prstkc` to Form-4 sales in this repo.

### Replay job shape
`scripts/night_book_i_buyback_divergence.py`, same header pattern as H;
`FAMILY` declared per the bundling decision made when H is scheduled.
Quarterly rebalance means `run_monthly`'s monthly loop needs a `rebalance_
months={3,6,9,12}`-shaped gate (or pre-aggregate the panel to quarterly `ym`
buckets before calling `run_monthly` — cheaper, reuses the engine unmodified,
preferred). State which approach was taken in the receipt.

---

## 3. Book J — the survivor combination (F + C_v1 + the DSR-surviving G3 lineage)

**Not literature-sourced.** This is the internal combination CLAUDE.md's
bottleneck section asks for once independent pieces exist: "a new mechanism
arrives as its own `PRODUCT_EXPERIMENT` book, never as a weight in
`arena_composite`... a learned router comes AFTER several independent
selectors exist, not before." Three pieces, EACH ALREADY WITH A RECEIPT (none
built here — J assembles, it does not re-derive):

### The three legs, exact receipts read 2026-09-13
1. **F — seasonality** (`seasonality_11_20_v0`, JKP `seas_11_15an` /
   `seas_16_20an`, top tercile, k=30, monthly): **$10M cell +0.43%/mo, t
   3.12**, by-era 1990s +0.46 / 2000s +0.32 / 2010-16 +0.17 / **2017-24 +0.76
   (t 2.30)** — the roadmap's own words, "the first engine with a
   current-era receipt at the floor." Verdict CONDITIONAL. Source: roadmap
   §11c "Third read", 2026-09-13 16:30, job family `NIGHT_JOB_BOOKS_2026_09_13`.
2. **C_v1 — disposition-overhang × announcement-window sign** (Amendment 2):
   **$3M cell +0.55%/mo, t 3.43**; $10M cell +0.33%/mo t 1.93; by-era at $10M
   0.24/0.53/0.03/0.38 (t 1.42). Placebo −0.18% (passes); momentum falsifier
   UNTESTABLE (momentum not alive on these rows) — same third-read table.
   Verdict CONDITIONAL, "more than doubles v0."
3. **G3 lineage `32f752af234f0d3d`** (representative genome
   `a85d7eb6323ab821`) — `backend/data/optimus/engines/
   G3_lineage_32f752af234f0d3d.json`, exported 2026-09-13T08:12:56Z: a linear
   composite of 14 within-month cross-sectional z-scores (`mom_12_1__xs
   -1.0, net_rev_4w__xs +1.0, ratio__xs -0.5, consensus_rev_1m__xs +0.5,
   disagreement__xs -1.0, drawdown_60d__xs +0.5, vol_60d__xs -0.5,
   log_market_cap__xs -1.0, ret_1m__xs -1.0, ret_6m__xs -0.5,
   coverage__xs 0.0, target_rev_1m__xs +1.0, log_close__xs +0.5,
   dispersion__xs -1.0`), k=20, equal-weight, **`hold_mult 8, hold_k 160`**
   (an 8-month staggered hold, not a plain monthly rebalance — carry this
   exactly, it is load-bearing for the lineage's own fitness), 25 bps/side,
   panel `backend/data/optimus/learner/train_table_long.parquet` (confirmed
   on disk: 925,757 rows, 143 columns, includes every z-scored feature the
   weight vector names — `mom_12_1, net_rev_4w, ratio, consensus_rev_1m,
   disagreement, dispersion, ret_1m, ret_6m, market_cap, close` all present).
   **`dsr_receipt`: DSR 1.000 > 0.95 bar, observed Sharpe 6.2735, expected
   maximum Sharpe 3.1528, 342 window banks met, 8,208 windows measured,
   verdict ACTIVE.** PBO **could not run** (`insufficient_windows`) — carry
   this as a stated gap, not a silent pass. `n_trials_raw` 595, `n_trials_
   effective_proxy` 251 (the ONC-clustered effective count does not exist on
   disk; the proxy over-counts independent trials and both numbers are
   reported). **The search itself is CONDITIONAL**, not clean: null genomes
   were not held to the arm's own drawdown refusal (69.3% of live candidates
   refused vs 0% of nulls — CLAUDE.md's own dated lesson), and the archive
   represented 248/251 lineages by a single window bank; THIS lineage is the
   stated exception (342 banks met). **The rule is FIXED** — the receipt says
   explicitly "re-running the evolutionary search... would be a new search
   with a new multiplicity budget, and the deflated Sharpe that licensed this
   row would not apply to the result." J must NOT re-search; it replays the
   frozen weight vector exactly.

### Construction
Risk-parity-weighted sleeve allocation, not equal notional — the round-3
note's own rule, because the three sleeves have very different realised vol
(F: a slow tercile cut, monthly; C_v1: a conditional cross-sectional tilt,
monthly; G3: an 8-month staggered hold with an observed Sharpe of 6.27, an
outlier scale that equal-notional weighting would let dominate). Weight each
sleeve by `1 / trailing_36m_vol_of_its_own_difference_series`, normalized to
sum to 1, recomputed monthly on a TRAILING window only (no look-ahead into
the weight itself). Each sleeve keeps its OWN frozen contract, own twin, own
floor pair — the combined book's return is `Σ w_i × (sleeve_i's net return −
sleeve_i's own twin's net return)`, i.e. the combination is graded as a
combination of EXCESS series, not of raw returns (so the combined book's
"twin" is implicitly the weighted sum of three already-graded twins, not a
fourth new random draw — state this explicitly, it is the one place this book
departs from the standard engine).

### The falsifiable combination — a THIRD twin required
Per the round-3 note: grade the combined book against a **RANDOM-sleeve-
selection twin** drawn from the SAME candidate pool this combination came
from (i.e., a book that risk-parity-weights three RANDOMLY chosen
`PRODUCT_EXPERIMENT`/`CONDITIONAL` candidates from the registry, not
necessarily orthogonal ones) — so the claim "these three specifically combine
well because they are different error types" is falsifiable against "any
three combine about this well because diversification alone helps." If the
named combination does not beat the random-triple twin, "different errors,
not more weights" is not supported by this instance even if the combined
Sharpe looks good in isolation.

### Falsifier (in addition to the random-triple twin above)
**Pairwise realized correlation of the three sleeves' monthly excess-return
series.** If any pair exceeds ~0.3 (the round-3 note's own threshold), the
"different errors" premise needs re-examination BEFORE the combination number
is read as support for it — report the three pairwise correlations first, the
combined Sharpe second. A second, cheaper falsifier: **drop each leg one at a
time** (three 2-sleeve combinations) — if a 2-sleeve combination matches or
beats the 3-sleeve number, the third leg is not pulling weight and the
"three independent sleeves" framing should say so plainly.

### Ruler
**None published** — this is a within-house combination question. The
practitioner number cited in the round-3 note (momentum + min-vol, Sharpe
0.96 vs components' 0.61/0.90) is explicitly flagged there as "weaker
evidence... not peer-reviewed," used only as a plausibility check that
diversification CAN move Sharpe by that much, never as this book's target.
**The twin (both the standard turnover-matched one implicit in each sleeve,
and the random-triple twin above) IS the ruler.**

### Decision rule
- `PRODUCT_PROMISING`: combined Sharpe beats the random-triple twin's Sharpe
  by a margin at least as large as one sleeve's own individual MDE-scale
  effect, AND no pairwise correlation exceeds 0.3, AND all three individual-
  drop tests show a positive marginal contribution.
- `FAILED_VARIANT`: the combined book underperforms the random-triple twin,
  OR any pairwise correlation exceeds 0.3 unexplained, OR the G3 leg's PBO
  eventually computes and fails (carry as `CANNOT_DETERMINE` until then, not
  as a pass).
- **This book inherits the WEAKEST standing verdict among its legs** — F and
  C_v1 are both CONDITIONAL and the G3 search itself is CONDITIONAL (the
  drawdown-refusal asymmetry). J cannot be `PRODUCT_PROMISING` on a stronger
  footing than its shakiest leg; state the inherited caveat on every receipt.
- Crash override and contamination clause as in §0, applied per-sleeve AND to
  the combined series.

### Replay job shape
`scripts/night_book_j_survivor_combo.py` — this is an AGGREGATOR, not a new
`run_monthly` call: it reads the three legs' own JSON receipts
(`night_factory_2026-09-13/*books_efg_replay*.json` for F, the C_v1
falsifier-job receipt, `engines/G3_lineage_32f752af234f0d3d.json` for G3),
re-derives each sleeve's monthly excess series from its stored `blocks`/
`excess` arrays (F and C_v1 already store these per `run_monthly`'s return
shape; G3's lineage export does not — a NEW replay of the frozen G3 rule
through `run_monthly`-shape bookkeeping is needed to get a compatible monthly
series, using the frozen weight vector and `train_table_long.parquet`,
**not** a re-search), computes the risk-parity weights, and combines. State
in the receipt which inputs were REPLAYED vs REUSED verbatim.

---

## 4. Book K — AI-washing / talk-vs-walk language (BLOCKED_ON_DATA, free pull needed)

### Mechanism, precursor
Boyuan Li (2025): the market prices AI "talk" (speculative disclosure
mentions) differently from AI "walk" (measured against workforce/patent/capex
investment) — talk-driven enthusiasm reverses over 1-2 years, walk sustains.
A related 2026 study: AI-washing elevates crash risk via inflated optimism.
**Not the same construction as the closed `text_jac`/`text_cos` test**
(confirmed: `NEGATIVE_RESULTS.md` §24, "Flow signals have MORE rank
information and LESS tradability" — `text_jac` (YoY 10-K whole-document
Jaccard change) t(IC) 7.47, t(net) 0.87, turnover 0.096; `text_cos` t(IC)
6.53, t(net) 0.10 — high IC, net-dead. That is WHOLE-DOCUMENT drift; AI-
washing needs CONTENT-TYPED mention density (the phrase "artificial
intelligence"/"AI", not generic textual distance), and the round-3 note's own
orthogonalization falsifier exists precisely to prove this is not the same
effect relabeled.

### Data — checked on disk 2026-09-13, NOT PRESENT
No 10-K/10-Q full-text body exists anywhere under `backend/data/optimus/`.
`backend/data/optimus/edgar_8k/` holds only `eightk_items.parquet`,
`eightk_rows.jsonl`, `checkpoint.json`, `company_tickers.json`,
`manifest.json` — **8-K item-tracking only, no 10-K/10-Q text, no full-text
search index**. No file, script, or module (`grep` across every `.py`) refers
to `text_jac`/`text_cos` outside `NEGATIVE_RESULTS.md` prose — whatever
produced that closed result is not on disk under any current name; treat it
as **NOT FOUND**, not as a reusable pipeline, and do not assume its code
exists to fork from (contradicts the round-3 note's claim that "the text
pipeline for `text_jac` already exists to fork from" — that pipeline could
not be located on this pass and the note's own wording should be corrected).
**BLOCKED_ON_DATA: mark this book blocked until the collector below lands.**

### Free source and collector spec
**SEC EDGAR full-text search API**, `https://efts.sec.gov/LATEST/search-
index?q=%22artificial+intelligence%22&forms=10-K,10-Q&dateRange=custom&
startdt=YYYY-MM-DD&enddt=YYYY-MM-DD&ciks=<CIK>` (paginated, `from`/`size`
params, JSON response with `hits.hits[]._source` carrying `file_date`, `ciks`,
`display_names`, `_id` = accession+filename). **Coverage: 2001-01-01 to
present only** (EDGAR full-text search does not index filings before 2001,
regardless of filer). Rate limit: 10 req/s per SEC's fair-access policy, no
key required (same limit `edgartools`/`companyfacts` already use in this
repo's data-acquisition notes). Cost: **FREE**, incremental pull cost is
request count only. For MENTION DENSITY (not just a hit/no-hit flag), the
actual filing document must be fetched (`https://www.sec.gov/Archives/edgar/
data/<CIK>/<accession-no-dashes>/<filename>`) and the "artificial
intelligence"/"AI" (word-boundary, case-sensitive to avoid "Aa"/plural-noise
false positives — verify against a hand-labeled sample) term frequency
counted per filing, normalized by document length, with the YoY change as the
"talk" feature. Rows/years: unknown until pulled — mark **NOT FOUND** for an
exact count; EDGAR full-text search covers all 10-K/10-Q filers 2001-2025,
so the eventual row count is filer-years × ~1 filing/year for 10-K, ~3/year
for 10-Q, order of magnitude in the hundreds of thousands across the full
universe, but no number should be quoted until the pull's own receipt exists.

### PIT rule
`file_date` from the full-text search hit IS the public filing date (EDGAR's
own index, not a derived timestamp) — same-day availability is defensible at
end-of-filing-day per the pattern `sec_insider_bulk.py` already established
for Form-4 (`FILING_DATE_EOD_CONSERVATIVE`); reuse that convention name for
consistency across collectors.

### Construction (once the pull exists)
Talk-minus-walk divergence score = z(YoY change in AI-mention density) minus
z(YoY change in a "walk" proxy — R&D/capex growth from `comp__funda.parquet`'s
`xrd`/`capxy`, or hiring growth from Book L if it exists by then, whichever
lands first). `pool_filter`: names with ≥ 2 consecutive years of 10-K
full-text coverage (so a YoY change is computable) — a coverage-selection
falsifier is required for the SAME reason F's twenty-year-tape skew needed one.

### Falsifiers
1. **Sign test, run separately**: the house prior (LLM/agent-alpha family,
   §19; option O/S ratio, §27) is that naive "more of X talk" signals INVERT
   — score both a long-talk and a short-talk leg and report both; do not
   pre-commit to the "more AI talk = bullish" direction the naive reading of
   the literature might suggest.
2. **Orthogonalize against `text_jac`/`text_cos`'s construction** (whole-
   document YoY cosine/Jaccard change) recomputed on the SAME filings, to
   confirm the AI-specific mention-density score is not the closed whole-
   document-drift effect relabeled with a narrower vocabulary.

### Ruler
**Not found** — both cited papers (2025-26) are event-study/crash-risk
shaped, not portfolio backtests. No monthly spread number exists to size
against; use the same conservative 0.65%/month declared-effect convention as
F/H until a better number surfaces.

### What ships tomorrow, and what does not
A builder CAN spec and START the EDGAR full-text collector tomorrow (Sonnet
data-acquisition, chunk-4-shaped: cursor file, resumable, receipt per run,
rows/new/dupes/failures — copy `scripts/news_pull.py`'s N-A shape). The
REPLAY job cannot be written until that pull has produced at least 2
consecutive years of coverage for a meaningful `pool_filter` band — this is
the one book in this batch where "builder spec" means "collector spec," not
"replay job," for its first deliverable.

---

## 5. Book L — universe-wide hiring-rate factor (BLOCKED_ON_DATA, extends TRIAL-HIRING-PIVOT-1)

### Relationship to TRIAL-HIRING-PIVOT-1 (N-G)
N-G (roadmap §3 lane N, pre-register-before-collector) is scoped to **three
named instances** (ADBE, ADSK, GPRO), testing the specific pivot-to-AI
hypothesis, with control = same-sector names with no AI-role-share change and
placebo = the feature shifted +90 days, primary = 63-session SPY-adjusted
return. **Book L is a SEPARATE, broader cross-sectional trial** — universe-
wide hiring-RATE (not AI-role share specifically), a genuinely different
mechanism (labor-input, not sector-pivot-narrative), sharing only the
collector, not the prereg. Do not fold L into N-G's registration; it needs its
own.

### Data — checked 2026-09-13, NOT PRESENT
No file, script, or module referencing `greenhouse`, `lever.co`, or `ashbyhq`
exists anywhere in the repo (`grep -rl` across every `.py`, zero hits); no
`*hiring*`-named file exists under `backend/` or `scripts/`. **Confirmed
BLOCKED_ON_DATA** — this is a genuine, unbuilt collector, not a re-cut of
something already on disk.

### The tracker universe and coverage — figure to VERIFY, not assumed
This task cites "2,362 tradable names"; the ONLY universe-count figures
found on disk during this pass are `backend/data/funnel_cache/universe.json`
(`"n": 5324`, `"venues": 5` — a broader listed-names cache, not the tracker's
tradable-dollar-volume-filtered set) and the roadmap's own "~3,056" figure
(O8, dated 2026-09-09, "the tracker universe"). **Neither file matched
2,362 exactly on this pass** — the builder must load whichever file
`backend/services/agency.py`'s `TRADABLE_DOLLAR_VOL` constant currently
filters against (referenced at `agency.py:733` but not traced further here)
and print its live row count in the collector's first receipt, rather than
hardcoding any of these three numbers. **Coverage will be LOW and must be
stated as a fraction of whatever that live count is** — ATS-page existence
itself correlates with company size/sophistication (large tech/growth firms
post to Greenhouse/Lever/Ashby; small-caps, financials, utilities, REITs
mostly do not), which is exactly why the twin below is drawn from
ATS-covered names only.

### Collector spec: `scripts/hiring_pull.py`
**Boards and endpoint shapes** (public, no key, no login — verified against
each platform's own publicly documented API shape; not fetched live this
pass, cite and verify status codes at build time):
- **Greenhouse**: `https://boards-api.greenhouse.io/v1/boards/<board_token>/
  jobs?content=true` → JSON `{jobs: [{id, title, updated_at, location:
  {name}, content, departments: [...], offices: [...]}]}`. `board_token` is
  usually the company's lowercase name/slug, discoverable from the careers
  page URL (`https://boards.greenhouse.io/<board_token>`) or by probing common
  slug variants.
- **Lever**: `https://api.lever.co/v0/postings/<company>?mode=json` → JSON
  array `[{id, text (title), categories: {team, location, commitment},
  createdAt, hostedUrl}]`. `<company>` is the slug from
  `https://jobs.lever.co/<company>`.
- **Ashby**: `https://api.ashbyhq.com/posting-api/job-board/<board_name>` →
  JSON `{jobs: [{id, title, department, team, location, publishedAt,
  isListed}]}`. `<board_name>` is the slug from `https://jobs.ashbyhq.com/
  <board_name>`.

**Board-token map from the tracker universe**: no such map exists on disk.
Build it as a two-step process: (1) a small manually-curated seed map for the
Alpaca/tracker universe's largest, most likely-covered names (tech, biotech,
growth — the same names N-G already names: ADBE, ADSK, GPRO, plus S&P 500
tech/growth constituents), stored as `backend/data/board_token_map.json`
`{permno_or_symbol: {platform, token}}`; (2) an automated discovery pass that
probes `careers.<company-domain>.com` redirects and common slug guesses
(company name variants) against all three APIs, logging hits/misses per
symbol — this is the part with real false-negative risk (a company can run
Greenhouse under an unguessable token) and the collector's receipt must
report **probe attempts vs confirmed hits**, not just hits, so silent
under-coverage is visible (CLAUDE.md's own "silent fragility" rule).

**Cadence**: daily, incremental — each board's job list is small (tens to low
hundreds of postings), so a full re-pull per board per day is cheap; no
delta/cursor needed per board, but the CORPUS write is append-only with
`first_seen_utc` stamped at ingest (never derived from `updated_at`/
`createdAt`, which are index-state fields the source can silently backfill,
per the N-A "two PIT pitfalls" note already in the roadmap).

**Schema** (JSONL, one file per board per day, mirroring N-A's shape):
`{source: "greenhouse"|"lever"|"ashby", board_token, symbol, permno,
first_seen_utc, observed_date, job_id, title, department, location, is_ai_ml_
titled: bool, raw_id}`. `is_ai_ml_titled` = a regex/keyword match on `title`
(AI, ML, Machine Learning, Artificial Intelligence, Data Scientist, LLM,
Applied Scientist — the same vocabulary N-G's prereg should already define;
reuse it, do not redefine).

**Honest coverage**: reported as `(symbols with ≥ 1 confirmed ATS board) /
(live tracker-universe count, printed from source)` — expect this fraction to
be well under half; state it exactly, do not round up, and do not let the
book's `pool_filter` silently narrow to "whatever we found" without that
denominator printed beside it every time the number is used.

### PIT rule
`first_seen_utc` = first time THIS collector observed the posting (own
ingest clock), never the source's `updated_at`/`createdAt`/`publishedAt` —
those are index-state fields an ATS can backfill or edit silently, the same
caveat N-A already states for Google News RSS.

### Construction (once coverage exists)
Universe-wide hiring-rate = 90-day change in total open-role count per
issuer, normalized by trailing headcount proxy (market cap or Compustat
`emp` if present — check `comp__funda.parquet` for an `emp` column at build
time) — NOT the AI-role-share feature N-G already owns; that stays N-G's.
`pool_filter`: symbols with a confirmed ATS board (the coverage-selection
control named above). k = 30, monthly.

### Twin
Random draw from ATS-COVERED names only (per the round-3 note's own stated
falsifier: ATS-page existence correlates with size/sophistication, so a twin
drawn from the FULL universe would measure "does this company have a careers
page" as much as "is it hiring faster").

### Falsifiers
1. **Size/momentum orthogonalization**: hiring firms may simply be momentum
   winners (growing companies hire and their stock has been rising); regress
   the hiring-rate signal's return against `mom_12_1` and `log_market_cap` and
   confirm it survives.
2. **Sector-neutral cut**: tech-sector hiring correlates with tech-sector
   beta generally; recompute within-sector (GICS or the tracker's own sector
   field) and confirm the effect is not purely a sector bet.

### Ruler
Kuehn-Simutin-Wang (2017, *J. Finance* 72(5)): 6%/yr decile spread, t≈3.66 —
**the citable number** (≈0.5%/mo order of magnitude); apply the standard
McLean-Pontiff ~50% post-publication-decay haircut as the working prior
(~0.25%/mo), since no 2020+ replication was found (flag **not found** for any
post-2020 confirmation) — this haircut is the round-3 note's own stated
convention, carried forward here rather than re-derived.

### What ships tomorrow, and what does not
Same shape as Book K: the COLLECTOR (`scripts/hiring_pull.py`, the board-
token seed map, the daily job, the coverage receipt) is buildable tomorrow as
a Sonnet data-acquisition task. The replay job waits on at least one full
coverage pass so the `pool_filter` denominator is a measured number, not a
guess.
